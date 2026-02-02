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
st.markdown("Menampilkan lokasi dan nama PTS langsung di peta.")

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
        query = "SELECT * FROM public.profil_pts"
        df = run_query(query)
        
        if df.empty:
            return pd.DataFrame()

        # Fix Error Timezone untuk Excel
        for col in df.select_dtypes(include=['datetimetz', 'datetime']).columns:
            df[col] = df[col].dt.tz_localize(None)

        # Bersihkan data teks
        text_cols = ['kode_pts', 'nama', 'status_pt', 'singkatan', 'alamat', 'kota_kab', 'provinsi']
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].fillna("-").astype(str)

        # Konversi Koordinat
        if 'latitude' in df.columns and 'longitude' in df.columns:
            df['lat'] = df['latitude'].astype(str).str.replace(',', '.', regex=False)
            df['lon'] = df['longitude'].astype(str).str.replace(',', '.', regex=False)
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        
        return df
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# =========================
# 4. VISUALISASI UTAMA
# =========================
df_pts = load_data_from_db()

if not df_pts.empty:
    df_map = df_pts.dropna(subset=['lat', 'lon'])

    # --- PENGATURAN PETA ---
    view_state = pdk.ViewState(latitude=-7.30, longitude=110.00, zoom=7, pitch=0)
    
    # Layer 1: Titik Merah (Kecil)
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position='[lon, lat]',
        get_color=[255, 0, 0, 200],
        get_radius=300,            # Ukuran titik diperkecil
        radius_min_pixels=2.5,     # Ukuran pixel terkecil
        pickable=True
    )

    # Layer 2: Label Nama (Ditampilkan Langsung)
    text_layer = pdk.Layer(
        "TextLayer",
        data=df_map,
        get_position='[lon, lat]',
        get_text="nama",
        get_size=11,               # Ukuran font nama
        get_color=[0, 50, 150],    # Warna biru gelap agar kontras
        get_angle=0,
        text_anchor="middle",
        alignment_baseline="bottom",
        pixel_offset=[0, -5]       # Menggeser teks sedikit ke atas titik
    )

    st.pydeck_chart(pdk.Deck(
        map_style=None,
        initial_view_state=view_state,
        layers=[scatter_layer, text_layer]
    ))
    
    # --- TABEL & EXCEL ---
    with st.expander("🔍 Lihat Tabel & Download Excel", expanded=True):
        st.dataframe(df_pts, use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_pts.to_excel(writer, index=False, sheet_name='Data_PTS')
            
        st.download_button(
            label="📄 Download Excel",
            data=buffer,
            file_name="data_pts_lengkap.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.warning("Data kosong.")
