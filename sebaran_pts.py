import os
import pandas as pd
import streamlit as st
import pydeck as pdk
from sqlalchemy import create_engine, text
from typing import Callable

# =========================
# 1. KONFIGURASI HALAMAN
# =========================
st.set_page_config(
    page_title="Peta Lokasi PTS Jawa",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 Peta Persebaran PTS di Jawa")
st.markdown("Aplikasi ini menampilkan lokasi PTS yang diambil langsung dari **Database Supabase**.")

# =========================
# 2. UTIL KONEKSI DATABASE
# (Diadaptasi dari 06_distribusi_pasien.py)
# =========================
def _build_query_runner() -> Callable[[str], pd.DataFrame]:
    """
    Mencoba membuat fungsi runner query.
    Prioritas 1: st.connection (Streamlit native)
    Prioritas 2: sqlalchemy engine (jika st.connection gagal/tidak dikonfigurasi)
    """
    # Cara 1: Coba Native Streamlit Connection
    try:
        conn = st.connection("postgresql", type="sql")
        def _run_query_streamlit(sql: str) -> pd.DataFrame:
            return conn.query(sql)
        # Test koneksi ringan
        _ = _run_query_streamlit("SELECT 1 as ok;")
        return _run_query_streamlit
    except Exception:
        pass

    # Cara 2: Fallback menggunakan SQLAlchemy Engine
    db_url = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL", ""))
    if not db_url:
        st.error("❌ Koneksi DB tidak dikonfigurasi. Pastikan 'connections.postgresql' ada di secrets.toml atau environment variable 'DATABASE_URL' diset.")
        st.stop()
    
    engine = create_engine(db_url, pool_pre_ping=True)

    def _run_query_engine(sql: str) -> pd.DataFrame:
        with engine.connect() as con:
            return pd.read_sql(text(sql), con)
    return _run_query_engine

# Inisialisasi runner query
run_query = _build_query_runner()

# =========================
# 3. FUNGSI PEMROSESAN DATA
# =========================
@st.cache_data(ttl=300) # Cache data selama 5 menit
def load_data_from_db():
    try:
        # Query mengambil semua data dari tabel profil_pts
        query = """
            SELECT 
                nama, 
                alamat, 
                kota_kab, 
                provinsi, 
                website, 
                latitude, 
                longitude 
            FROM public.profil_pts
        """
        df = run_query(query)
        
        if df.empty:
            return pd.DataFrame()

        # --- MAPPING KOLOM ---
        # Menyesuaikan nama kolom dari DB ke nama variabel internal yang dipakai di visualisasi
        # DB: kota_kab -> Internal: kota
        # DB: provinsi -> Internal: propinsi
        # DB: latitude -> Internal: lat_raw
        # DB: longitude -> Internal: lon_raw
        df = df.rename(columns={
            'kota_kab': 'kota',
            'provinsi': 'propinsi',
            'latitude': 'lat_raw',
            'longitude': 'lon_raw'
        })
        
        # Isi data kosong pada kolom teks
        text_cols = ['alamat', 'propinsi', 'kota', 'website', 'nama']
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].fillna("-").astype(str)

        # --- BERSIHKAN KOORDINAT ---
        # Karena di DB tipe datanya varchar(50) dan mungkin berisi koma (misal "-6,123")
        # Kita ganti koma jadi titik, lalu convert ke float
        df['lat'] = df['lat_raw'].astype(str).str.replace(',', '.', regex=False)
        df['lon'] = df['lon_raw'].astype(str).str.replace(',', '.', regex=False)
        
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        
        # Hapus baris yang koordinatnya invalid/kosong
        df = df.dropna(subset=['lat', 'lon'])
        
        return df

    except Exception as e:
        st.error(f"Error saat mengambil data dari database: {e}")
        return pd.DataFrame()

# =========================
# 4. VISUALISASI UTAMA
# =========================

# Load data langsung saat aplikasi dibuka
with st.spinner("Mengambil data dari Supabase..."):
    df_pts = load_data_from_db()

if not df_pts.empty:
    st.success(f"✅ Data berhasil dimuat: {len(df_pts)} kampus ditemukan.")
    
    # --- KONFIGURASI PETA ---
    # Hitung tengah peta berdasarkan rata-rata koordinat data
    view_state = pdk.ViewState(
        latitude=df_pts['lat'].mean(),
        longitude=df_pts['lon'].mean(),
        zoom=6,
        pitch=0
    )

    # Layer 1: Titik (Scatter)
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_pts,
        get_position='[lon, lat]',
        get_color=[255, 0, 0, 200], # Merah transparan
        
        # Pengaturan Ukuran Titik
        get_radius=1000,            
        radius_min_pixels=3,        
        radius_max_pixels=10,       
        
        pickable=True,
        auto_highlight=True
    )

    # Layer 2: Teks Nama
    text_layer = pdk.Layer(
        "TextLayer",
        data=df_pts,
        get_position='[lon, lat]',
        get_text="nama",
        get_size=12,
        get_color=[0, 0, 100], # Biru gelap
        get_angle=0,
        text_anchor="middle",
        alignment_baseline="bottom",
        billboard=True # Teks selalu menghadap user meskipun peta diputar
    )

    # Tooltip (Pop-up saat hover)
    tooltip = {
        "html": """
            <b>{nama}</b><br/>
            <small>{alamat}</small><br/>
            {kota}, {propinsi}<br/>
            <i>{website}</i>
        """,
        "style": {
            "backgroundColor": "white", 
            "color": "black",
            "fontSize": "12px",
            "padding": "10px",
            "borderRadius": "5px",
            "border": "1px solid #ccc"
        }
    }

    # Render Peta
    st.pydeck_chart(pdk.Deck(
        map_style='mapbox://styles/mapbox/light-v9', # Style peta terang
        initial_view_state=view_state,
        layers=[scatter_layer, text_layer],
        tooltip=tooltip
    ))
    
    # Tabel Data
    with st.expander("Lihat Data Tabel"):
        # Tampilkan kolom yang relevan untuk user
        cols_display = ['nama', 'alamat', 'kota', 'propinsi', 'website', 'lat', 'lon']
        st.dataframe(df_pts[cols_display])

else:
    st.warning("Data tidak ditemukan atau tabel kosong.")