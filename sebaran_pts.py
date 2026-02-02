import os
import io  # Library untuk handle file buffer
import pandas as pd
import streamlit as st
import pydeck as pdk
from sqlalchemy import create_engine, text
from typing import Callable

# =========================
# 1. KONFIGURASI HALAMAN
# =========================
st.set_page_config(
    page_title="Peta Lokasi PTS",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 Peta Persebaran PTS")
st.markdown("Aplikasi ini menampilkan lokasi PTS yang diambil langsung dari **Database**.")

# =========================
# 2. UTIL KONEKSI DATABASE
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
        # Query mengambil SEMUA data dari tabel profil_pts
        query = """
            SELECT 
                id,
                kode_pts,
                nama,
                status_pt,
                singkatan,
                alamat,
                kota_kab,
                provinsi,
                kode_pos,
                latitude,
                longitude,
                no_telp,
                no_fax,
                email,
                website,
                created_at
            FROM public.profil_pts
        """
        df = run_query(query)
        
        if df.empty:
            return pd.DataFrame()

        # --- MAPPING KOLOM ---
        # Rename agar konsisten dengan variabel yang dipakai
        df = df.rename(columns={
            'kota_kab': 'kota',
            'provinsi': 'propinsi',
            'latitude': 'lat_raw',
            'longitude': 'lon_raw'
        })
        
        # Isi data kosong pada kolom teks dengan "-"
        text_cols = [
            'kode_pts', 'nama', 'status_pt', 'singkatan', 'alamat', 
            'kota', 'propinsi', 'kode_pos', 'no_telp', 'no_fax', 
            'email', 'website'
        ]
        
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].fillna("-").astype(str)

        # --- BERSIHKAN KOORDINAT ---
        # Ubah koma jadi titik untuk latitude/longitude
        df['lat'] = df['lat_raw'].astype(str).str.replace(',', '.', regex=False)
        df['lon'] = df['lon_raw'].astype(str).str.replace(',', '.', regex=False)
        
        # Konversi ke numeric (float)
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        
        # Hapus baris yang koordinatnya invalid/kosong agar peta tidak error
        df = df.dropna(subset=['lat', 'lon'])
        
        return df

    except Exception as e:
        st.error(f"Error saat mengambil data dari database: {e}")
        return pd.DataFrame()

# =========================
# 4. VISUALISASI UTAMA
# =========================

# Load data langsung saat aplikasi dibuka
with st.spinner("Mengambil data dari Database..."):
    df_pts = load_data_from_db()

if not df_pts.empty:
    st.success(f"✅ Data berhasil dimuat: {len(df_pts)} kampus ditemukan.")
    
    # --- KONFIGURASI PETA ---
    # Hitung tengah peta secara default (Pulau Jawa)
    view_state = pdk.ViewState(
            latitude=-7.30,    
            longitude=110.00,  
            zoom=6.8,          
            pitch=0
        )

    # Layer 1: Titik (Scatter) - Merah
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_pts,
        get_position='[lon, lat]',
        get_color=[255, 0, 0, 200], 
        get_radius=1000,            
        radius_min_pixels=3,        
        radius_max_pixels=10,       
        pickable=True,
        auto_highlight=True
    )

    # Layer 2: Teks Nama - Biru
    text_layer = pdk.Layer(
        "TextLayer",
        data=df_pts,
        get_position='[lon, lat]',
        get_text="nama",
        get_size=12,
        get_color=[0, 0, 100], 
        get_angle=0,
        text_anchor="middle",
        alignment_baseline="bottom",
        billboard=True 
    )

    # Tooltip (Pop-up saat mouse hover)
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
        map_style=None,
        initial_view_state=view_state,
        layers=[scatter_layer, text_layer],
        tooltip=tooltip
    ))
    
    # --- BAGIAN TABEL DAN DOWNLOAD ---
    with st.expander("Lihat Data Tabel", expanded=False):
        # Daftar kolom lengkap untuk ditampilkan
        # Note: 'kota' dan 'propinsi' adalah nama baru setelah di-rename di fungsi load
        cols_display = [
            'id', 'kode_pts', 'nama', 'status_pt', 'singkatan', 
            'alamat', 'kota', 'propinsi', 'kode_pos', 
            'lat_raw', 'lon_raw', 'no_telp', 'no_fax', 
            'email', 'website', 'created_at'
        ]
        
        # Tampilkan DataFrame di layar
        st.dataframe(df_pts[cols_display])

        st.write("---")
        st.write("📥 **Unduh Data**")
        
        # 1. Siapkan buffer di memori
        buffer = io.BytesIO()
        
        # --- PERBAIKAN ERROR TIMEZONE DISINI ---
        # Buat copy dataframe khusus export agar tidak mengganggu df utama
        df_export = df_pts[cols_display].copy()

        # Cek dan bersihkan kolom created_at dari zona waktu (Timezone-aware -> Timezone-naive)
        if 'created_at' in df_export.columns:
            # Pastikan tipe datanya datetime, lalu buang info timezone
            df_export['created_at'] = pd.to_datetime(df_export['created_at']).dt.tz_localize(None)

        # 2. Tulis DataFrame ke buffer sebagai Excel
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Data PTS')
            
            # Format Excel agar rapi (Text Wrap dan lebar kolom)
            workbook  = writer.book
            worksheet = writer.sheets['Data PTS']
            format_wrap = workbook.add_format({'text_wrap': True, 'valign': 'top'})
            
            # Set lebar kolom A sampai P (16 kolom)
            worksheet.set_column('A:P', 20, format_wrap)

        # 3. Tombol Download
        st.download_button(
            label="📄 Download File Excel (.xlsx)",
            data=buffer,
            file_name="data_pts_lengkap.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.warning("Data tidak ditemukan atau tabel kosong.")
