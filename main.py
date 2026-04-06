import runpy
import os
import streamlit as st
from streamlit_option_menu import option_menu

# -----------------------------
# 1. Konfigurasi Halaman Utama
# -----------------------------
# Konfigurasi ini akan menjadi default untuk semua sub-halaman
st.set_page_config(
    page_title="Dashboard Analisis PTS",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# 2. Definisi Menu & Icon
# -----------------------------
# Sesuaikan nama menu dengan file Python yang ingin dijalankan
MENU_ITEMS = {
    "🗺️ Peta Persebaran PTS Jawa": "sebaran_pts.py",
    "🚂 Jarak PTS ke Rel Kereta": "pts_dekat_rel.py",
}

# Icon Bootstrap yang digunakan untuk masing-masing menu
# (https://icons.getbootstrap.com/)
MENU_ICONS = ["map", "train-front"]

# -----------------------------
# 3. Main App (Logika Sidebar & Navigasi)
# -----------------------------
def main():
    
    with st.sidebar:
        st.markdown("### 📁 Menu Utama")
        
        # Membuat opsi menu menggunakan streamlit-option-menu
        selection = option_menu(
            menu_title=None, # Menyembunyikan judul bawaan option_menu
            options=list(MENU_ITEMS.keys()),
            icons=MENU_ICONS,
            default_index=0,
            orientation="vertical",
            styles={
                "container": {"padding": "0!important", "background-color": "transparent"},
                "nav-link": {"font-size": "15px", "text-align": "left", "margin":"0px", "--hover-color": "#eee"},
                "nav-link-selected": {"background-color": "#4CAF50"}, # Warna hijau saat dipilih
            }
        )

        st.divider()
        st.caption("Pusat Data Perguruan Tinggi Swasta")

    # Mengeksekusi file Python berdasarkan pilihan menu di sidebar
    page_path = MENU_ITEMS[selection]
    
    try:
        # Menjalankan file python terpilih
        runpy.run_path(page_path, run_name="__main__")
    except FileNotFoundError:
        st.error(f"❌ File halaman tidak ditemukan: `{page_path}`. Pastikan file berada di folder yang sama dengan `main.py`.")
    except Exception as e:
        st.error(f"❌ Terjadi kesalahan saat menjalankan `{page_path}`:")
        st.exception(e)


if __name__ == "__main__":
    main()