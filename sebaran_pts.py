import os
import io
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
st.markdown("Aplikasi ini menampilkan data lengkap PTS langsung dari database.")

# =========================
# 2. UTIL KONEKSI DATABASE
# =========================
def _build_query_runner() -> Callable[[str], pd.DataFrame]:
    """Menangani koneksi database baik di lokal maupun Streamlit Cloud"""
    try:
        # Coba koneksi native Streamlit
        conn = st.connection("postgresql", type="sql")
        def _run_query_streamlit(sql: str) -> pd.DataFrame:
            return conn.query(sql)
        _ = _run_query_streamlit("SELECT 1 as ok;")
        return _run_query_streamlit
    except Exception:
        pass

    # Fallback ke SQLAlchemy engine
    db_url = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL", ""))
    if not db_url:
        st.error("❌ Koneksi DB tidak dikonfigurasi. Periksa secrets.toml atau Env Var.")
        st.stop()
    
    engine = create_engine(db_url, pool_pre_ping=True)
    def _run_query_engine(sql: str) -> pd.DataFrame:
        with engine.connect() as con:
            return pd.read_sql(text(sql), con)
    return _run_query_engine

run_query = _build_query_runner()

# =========================
# 3. FUNGSI PEMROSESAN DATA
# =========================
@st.cache_data(ttl=300)
def load_data_from_db():
    try:
        # Mengambil semua kolom sesuai struktur tabel profil_pts
        query = "SELECT * FROM public.profil_pts"
        df = run_query(query)
        
        if df.empty:
            return pd.DataFrame()

        # --- FIX ERROR EXCEL: Hilangkan Timezone ---
        # Menghapus info timezone agar kompatibel dengan format .xlsx
        for col in df.select_dtypes(include=['datetimetz', 'datetime']).columns:
            df[col] = df[col].dt.tz_localize(None)

        # --- BERSIHKAN DATA TEKS ---
        text_cols = [
            'kode_pts', 'nama', 'status_pt', 'singkatan', 'alamat', 
            'kota_kab', 'provinsi', 'kode_pos', 'no_telp', 
            'no_fax', 'email', 'website'
        ]
        
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].fillna("-").astype(str)

        # --- KONVERSI KOORDINAT ---
        if 'latitude' in df.columns and 'longitude' in df.columns:
            # Mengubah format koma (,) menjadi titik (.) jika ada
            df['lat'] = df['latitude'].astype(str).str.replace(',', '.', regex=False)
            df['lon'] = df['longitude'].astype(str).str.replace(',', '.', regex=False)
            
            # Konversi ke numerik
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        
        return df

    except Exception as e:
        st.error(f"Error saat mengambil data dari database: {e}")
        return pd.DataFrame()

# =========================
# 4. VISUALISASI UTAMA
# =========================
with st.spinner("Sedang memproses data..."):
    df_pts = load_data_from_db()

if not df_pts.empty:
    st.success(f"✅ Berhasil memuat {len(df_pts)} data kampus.")
    
    # Filter hanya data yang punya koordinat untuk ditampilkan di peta
    df_map = df_pts.dropna(subset=['lat', 'lon'])

    # --- PENGATURAN PETA (PYDECK) ---
    view_state = pdk.ViewState(
        latitude=-7.30, 
        longitude=110.00, 
        zoom=6.5, 
        pitch=0
    )
    
    # Layer titik merah
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position='[lon, lat]',
        get_color=[255, 75, 75, 180], # Merah sedikit transparan
        get_radius=400,              # Radius dalam meter (DIPERKECIL)
        radius_min_pixels=2.5,       # Ukuran pixel terkecil (DIPERKECIL)
        radius_max_pixels=12,        # Ukuran pixel terbesar saat zoom in
        pickable=True,
        auto_highlight=True
    )

    # Tooltip saat mouse diarahkan ke titik
    tooltip_config = {
        "html": "<b>{nama}</b><br/>{kota_kab}, {provinsi}<br/>Status: {status_pt}",
        "style": {"backgroundColor": "steelblue", "color": "white"}
    }

    st.pydeck_chart(pdk.Deck(
        map_style=None, # Style peta terang
        initial_view_state=view_state,
        layers=[scatter_layer],
        tooltip=tooltip_config
    ))
    
    # --- TABEL DATA LENGKAP ---
    st.write("### 🔍 Detail Data PTS")
    with st.expander("Klik untuk melihat tabel data lengkap", expanded=False):
        # Urutan kolom yang ingin ditampilkan di UI
        display_order = [
            'id', 'kode_pts', 'nama', 'singkatan', 'status_pt', 
            'alamat', 'kota_kab', 'provinsi', 'email', 'website'
        ]
        # Pastikan hanya menampilkan kolom yang ada
        cols_available = [c for c in display_order if c in df_pts.columns]
        st.dataframe(df_pts[cols_available], use_container_width=True)

        # --- FITUR DOWNLOAD EXCEL ---
        st.markdown("#### 📥 Download Data")
        
        buffer = io.BytesIO()
        # Menggunakan XlsxWriter sebagai engine
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            # Mengunduh SELURUH kolom dari dataframe (termasuk created_at)
            df_pts.to_excel(writer, index=False, sheet_name='Profil_PTS')
            
            # Mempercantik tampilan Excel
            workbook  = writer.book
            worksheet = writer.sheets['Profil_PTS']
            
            header_format = workbook.add_format({
                'bold': True, 
                'bg_color': '#F2F2F2', 
                'border': 1
            })
            
            # Set lebar kolom otomatis sederhana
            for col_num, value in enumerate(df_pts.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 18)

        st.download_button(
            label="📄 Download File Excel (.xlsx)",
            data=buffer,
            file_name="data_profil_pts_lengkap.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.warning("Data tidak ditemukan. Pastikan tabel 'public.profil_pts' sudah terisi.")

# Penutup
st.divider()
st.caption("Aplikasi Pemetaan PTS | Versi 2.0")

