import os
import io
import pandas as pd
import streamlit as st
import requests
import geopandas as gpd
from shapely.geometry import LineString
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine, text
from typing import Callable

# =========================
# 1. KONFIGURASI HALAMAN
# =========================
# st.set_page_config(page_title="Analisis Jarak PTS ke Rel Kereta", layout="wide", page_icon="🚂")

st.title("🚂 Analisis Jarak Perguruan Tinggi ke Rel Kereta Api (Pulau Jawa)")
st.write("Aplikasi ini menghitung jarak terdekat dari setiap Perguruan Tinggi Swasta (PTS) ke jalur rel kereta api di Pulau Jawa berdasarkan radius yang Anda tentukan. Data diambil secara *real-time* dari Database.")

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

run_query = _build_query_runner()

# =========================
# 3. FUNGSI AMBIL DATA
# =========================
@st.cache_data(ttl=300) # Cache data selama 5 menit
def load_data_from_db():
    try:
        # Ambil kolom yang diperlukan saja untuk mempercepat proses
        query = """
            SELECT 
                kode_pts,
                nama,
                kota_kab,
                latitude,
                longitude
            FROM public.profil_pts
        """
        df = run_query(query)
        
        if df.empty:
            return pd.DataFrame()

        # Mapping kolom agar serasi dengan kode filter geospasial
        df = df.rename(columns={
            'kode_pts': 'Kode PTS',
            'nama': 'Nama PTS',
            'kota_kab': 'Kota/Kab',
            'latitude': 'Latitude_raw',
            'longitude': 'Longitude_raw'
        })
        
        # Bersihkan koordinat (ubah koma jadi titik)
        df['Latitude'] = df['Latitude_raw'].astype(str).str.replace(',', '.', regex=False)
        df['Longitude'] = df['Longitude_raw'].astype(str).str.replace(',', '.', regex=False)
        
        # Konversi ke numerik
        df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
        df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
        
        # Buang data yang tidak punya koordinat valid
        df = df.dropna(subset=['Latitude', 'Longitude'])
        
        return df

    except Exception as e:
        st.error(f"Error saat mengambil data dari database: {e}")
        return pd.DataFrame()

@st.cache_data(show_spinner="Mengunduh data rel kereta api dari OpenStreetMap...")
def get_railway_data():
    overpass_url = "https://overpass.kumi.systems/api/interpreter"
    overpass_query = """
    [out:json];
    (
      way["railway"="rail"](-8.8, 105.0, -5.8, 115.0);
      way["railway"="narrow_gauge"](-8.8, 105.0, -5.8, 115.0);
    );
    out geom;
    """
    response = requests.post(overpass_url, data={'data': overpass_query})
    data = response.json()
    
    lines = []
    for element in data['elements']:
        if element['type'] == 'way':
            coords = [(node['lon'], node['lat']) for node in element['geometry']]
            if len(coords) >= 2:
                lines.append(LineString(coords))
                
    railways_gdf = gpd.GeoDataFrame(geometry=lines, crs="EPSG:4326")
    return railways_gdf

# =========================
# 4. PENGATURAN PENGGUNA
# =========================
with st.sidebar:
    st.header("⚙️ Pengaturan")
    st.info("Data dimuat otomatis dari Supabase/PostgreSQL.")
    
    # Slider untuk menentukan radius jarak (default 3 km / 3000 m)
    radius_km = st.slider("Batas Jarak ke Rel (Kilometer)", min_value=0.5, max_value=10.0, value=3.0, step=0.5)
    radius_m = radius_km * 1000

# =========================
# 5. LOGIKA UTAMA & TAMPILAN
# =========================
with st.spinner("Mengambil data PTS dari Database..."):
    df = load_data_from_db()

if not df.empty:
    st.success(f"✅ Berhasil memuat {len(df)} titik PTS dari Database.")
    
    # Ambil data rel kereta
    railways_gdf = get_railway_data()
    st.info(f"🚂 Berhasil memuat {len(railways_gdf)} segmen rel kereta api dari OpenStreetMap.")
    
    with st.spinner("Menghitung jarak spasial ke rel terdekat..."):
        # Buat GeoDataFrame PTS
        pts_gdf = gpd.GeoDataFrame(
            df, 
            geometry=gpd.points_from_xy(df.Longitude, df.Latitude), 
            crs="EPSG:4326"
        )
        
        # Proyeksi ke Web Mercator (EPSG:3857) untuk hitung jarak dalam meter
        rail_3857 = railways_gdf.to_crs("EPSG:3857")
        pts_3857 = pts_gdf.to_crs("EPSG:3857")
        
        # Hitung jarak terdekat
        pts_gdf['Jarak_ke_Rel_Meter'] = pts_3857.geometry.apply(lambda x: rail_3857.distance(x).min())
        
        # Filter berdasarkan slider
        hasil_filter = pts_gdf[pts_gdf['Jarak_ke_Rel_Meter'] <= radius_m].copy()
        hasil_filter['Jarak_ke_Rel_Meter'] = hasil_filter['Jarak_ke_Rel_Meter'].round(2)
        
    # --- TAMPILAN HASIL ---
    st.subheader(f"📑 Hasil Analisis (Terdapat {len(hasil_filter)} PTS dalam radius {radius_km} km)")
    
    # Kolom yang ditampilkan
    kolom_tampil = ['Kode PTS', 'Nama PTS', 'Kota/Kab', 'Jarak_ke_Rel_Meter', 'Latitude', 'Longitude']
    kolom_tampil = [col for col in kolom_tampil if col in hasil_filter.columns]
    
    # Tampilkan dataframe
    st.dataframe(hasil_filter[kolom_tampil].sort_values(by='Jarak_ke_Rel_Meter'), use_container_width=True)
    
    # --- TOMBOL DOWNLOAD EXCEL ---
    buffer = io.BytesIO()
    # Buat file excel di dalam memori (kolom 'geometry' dan '_raw' dibuang agar bersih)
    df_download = hasil_filter.drop(columns=['geometry', 'Latitude_raw', 'Longitude_raw'], errors='ignore')
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_download.to_excel(writer, index=False, sheet_name='Data PTS Filter')
    
    st.download_button(
        label="📥 Unduh Hasil Filter (Excel)",
        data=buffer.getvalue(),
        file_name=f"pts_dekat_rel_{radius_km}km.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    # --- PETA INTERAKTIF ---
    st.subheader("🗺️ Peta Lokasi PTS dan Rel Kereta Api")
    
    # Inisialisasi peta di tengah Pulau Jawa
    m = folium.Map(location=[-7.25, 110.0], zoom_start=7, tiles="CartoDB positron")
    
    # Tambahkan Rel Kereta ke peta
    folium.GeoJson(
        railways_gdf,
        name="Jalur Kereta Api",
        style_function=lambda x: {'color': 'red', 'weight': 2, 'opacity': 0.7}
    ).add_to(m)
    
    # Tambahkan marker PTS yang masuk kriteria
    for idx, row in hasil_filter.iterrows():
        popup_text = f"<b>{row.get('Nama PTS', 'Tidak diketahui')}</b><br>Jarak: {row['Jarak_ke_Rel_Meter']} m"
        folium.CircleMarker(
            location=[row['Latitude'], row['Longitude']],
            radius=5,
            popup=folium.Popup(popup_text, max_width=300),
            color="blue",
            fill=True,
            fill_color="blue",
            fill_opacity=0.7
        ).add_to(m)
        
    # Tampilkan peta di Streamlit
    st_folium(m, width=1200, height=600, returned_objects=[])

else:
    st.warning("⚠️ Data PTS tidak ditemukan di dalam Database atau tidak ada koordinat valid.")
