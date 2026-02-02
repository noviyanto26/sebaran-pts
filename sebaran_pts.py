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
st.markdown("Aplikasi ini menampilkan data lengkap PTS dari database.")

# =========================
# 2. UTIL KONEKSI DATABASE
# =========================
def _build_query_runner() -> Callable[[str], pd.DataFrame]:
    try:
        conn = st.connection("postgresql", type="sql")
        def _run_query_streamlit(sql: str) -> pd.DataFrame:
            return conn.query(sql)
        _ = _run_query_streamlit("SELECT 1 as ok;")
        return _run_query_streamlit
    except Exception:
        pass

    db_url = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL", ""))
    if not db_url:
        st.error("❌ Koneksi DB tidak dikonfigurasi.")
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
        # Mengambil SEMUA kolom sesuai struktur tabel terbaru
        query = "SELECT * FROM public.profil_pts"
        df = run_query(query)
        
        if df.empty:
            return pd.DataFrame()

        # --- BERSIHKAN DATA ---
        # List semua kolom teks berdasarkan struktur tabel Anda
        text_cols = [
            'kode_pts', 'nama', 'status_pt', 'singkatan', 'alamat', 
            'kota_kab', 'provinsi', 'kode_pos', 'no_telp', 
            'no_fax', 'email', 'website'
        ]
        
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].fillna("-").astype(str)

        # --- KONVERSI KOORDINAT UNTUK PETA ---
        # Simpan nilai asli ke kolom 'lat' dan 'lon' untuk keperluan pydeck
        df['lat'] = df['latitude'].astype(str).str.replace(',', '.', regex=False)
        df['lon'] = df['longitude'].astype(str).str.replace(',', '.', regex=False)
        
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        
        return df

    except Exception as e:
        st.error(f"Error saat mengambil data: {e}")
        return pd.DataFrame()

# =========================
# 4. VISUALISASI UTAMA
# =========================
with st.spinner("Mengambil data..."):
    df_pts = load_data_from_db()

if not df_pts.empty:
    st.success(f"✅ Data berhasil dimuat: {len(df_pts)} PTS ditemukan.")
    
    # Filter data yang memiliki koordinat valid untuk Peta
    df_map = df_pts.dropna(subset=['lat', 'lon'])

    # --- RENDER PETA ---
    view_state = pdk.ViewState(latitude=-7.30, longitude=110.00, zoom=6, pitch=0)
    
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position='[lon, lat]',
        get_color=[255, 75, 75, 200],
        get_radius=2000,
        radius_min_pixels=4,
        pickable=True
    )

    st.pydeck_chart(pdk.Deck(
        map_style=None,
        initial_view_state=view_state,
        layers=[scatter_layer],
        tooltip={"text": "{nama}\n{kota_kab}, {provinsi}"}
    ))
    
    # --- TABEL DATA LENGKAP ---
    with st.expander("🔍 Lihat Tabel Data Lengkap", expanded=True):
        # Menyusun urutan kolom agar rapi di tabel
        cols_to_show = [
            'id', 'kode_pts', 'nama', 'singkatan', 'status_pt', 
            'alamat', 'kota_kab', 'provinsi', 'kode_pos', 
            'email', 'website', 'no_telp', 'latitude', 'longitude'
        ]
        
        # Filter kolom yang benar-benar ada di dataframe
        existing_cols = [c for c in cols_to_show if c in df_pts.columns]
        st.dataframe(df_pts[existing_cols], use_container_width=True)

        # --- FITUR DOWNLOAD EXCEL ---
        st.write("---")
        st.write("📥 **Unduh Data Lengkap**")
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            # Export semua kolom yang ada di database
            df_pts.to_excel(writer, index=False, sheet_name='Profil PTS')
            
            workbook  = writer.book
            worksheet = writer.sheets['Profil PTS']
            
            # Format header & auto-adjust (sederhana)
            header_format = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
            for col_num, value in enumerate(df_pts.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 15)

        st.download_button(
            label="📄 Download Seluruh Data ke Excel (.xlsx)",
            data=buffer,
            file_name="profil_pts_lengkap.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.warning("Data tidak ditemukan atau tabel kosong.")
