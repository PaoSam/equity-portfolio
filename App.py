import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date
import requests

# Configurazione Pagina
st.set_page_config(page_title="Equity Portfolio Paolo - Live IBKR", layout="wide")

# --- FUNZIONE PER LEGGERE I MARGINI DAL SITO IBKR ---
@st.cache_data(ttl=3600)  # Aggiorna i dati ogni ora per non essere bloccati
def get_ibkr_margins(url):
    try:
        # Simuliamo un browser reale per evitare blocchi
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=header, timeout=10)
        # Leggiamo tutte le tabelle presenti nella pagina
        tables = pd.read_html(response.text)
        
        margin_dict = {}
        for df in tables:
            # Cerchiamo le colonne giuste nella tabella (Underlying e Overnight Initial)
            if 'Underlying' in df.columns and 'Overnight Initial' in df.columns:
                for _, row in df.iterrows():
                    ticker = str(row['Underlying']).strip()
                    valore = str(row['Overnight Initial']).replace('$', '').replace(',', '')
                    try:
                        margin_dict[ticker] = float(valore)
                    except:
                        continue
        return margin_dict
    except Exception as e:
        st.error(f"Errore nella lettura live da IBKR: {e}")
        return {}

# --- CARICAMENTO DATI ---
def load_equity(uploaded_file):
    data = []
    try:
        content = uploaded_file.getvalue().decode("utf-8")
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) == 6:
                try:
                    date_obj = datetime.strptime(parts[0], '%d/%m/%Y')
                    pnl = float(parts[1])
                    data.append({'date': date_obj, 'pnl': pnl})
                except: continue
    except: return None
    if not data: return None
    df = pd.DataFrame(data)
    df = df.groupby('date')['pnl'].sum().reset_index()
    df = df.sort_values('date')
    return df

st.markdown("# 📈 Analisi Equity & Margini LIVE da IBKR")

# Esecuzione della lettura dal sito
url_ibkr = "https://www.interactivebrokers.com/en/trading/margin-futures-fops.php"
with st.spinner('Recupero margini in tempo reale da Interactive Brokers...'):
    live_margins = get_ibkr_margins(url_ibkr)

if live_margins:
    st.success(f"✅ Rilevati correttamente {len(live_margins)} strumenti dal sito IBKR.")
else:
    st.warning("⚠️ Impossibile leggere i dati live. Utilizzo database di emergenza.")
    live_margins = {"GC": 52892.98, "NQ": 18480, "ES": 12320, "MNQ": 1848}

# --- CARICAMENTO FILE ---
uploaded_files = st.file_uploader("Carica i file TXT da Titan", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = []
    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())

    if raw_data:
        st.sidebar.header("💰 Margini Rilevati (Live)")
        margine_totale = 0
        dettaglio_selezione = []

        st.write("### 🛠️ Strategie e Margini")
        selected_names = []
        cols = st.columns(min(len(raw_data), 4))
        
        for i, name in enumerate(sorted(raw_data.keys())):
            m_val = 0
            t_found = "N/A"
            # Cerchiamo il ticker nel nome del file tra quelli letti dal sito
            for t in live_margins:
                if t in name.upper():
                    m_val = live_margins[t]
                    t_found = t
                    break
            
            with cols[i % 4]:
                if st.checkbox(f"{name} (${m_val:,.2f})", value=True, key=name):
                    selected_names.append(name)
                    margine_totale += m_val
                    if m_val > 0:
                        dettaglio_selezione.append({"Ticker": t_found, "Margine": m_val})

        if selected_names:
            st.sidebar.metric("Margine Totale Live", f"${margine_totale:,.2f}")
            if dettaglio_selezione:
                st.sidebar.write("**Dettaglio Strumenti:**")
                st.sidebar.dataframe(pd.DataFrame(dettaglio_selezione).drop_duplicates('Ticker'), hide_index=True)

            # --- ELABORAZIONE GRAFICO ---
            df_port = pd.DataFrame({'date': sorted(list(set(all_dates)))})
            for name in selected_names:
                df_port = df_port.merge(raw_data[name][['date', 'pnl']].rename(columns={'pnl': name + '_pnl'}), on='date', how='left')
            
            df_port.fillna(0, inplace=True)
            
            start_d = st.sidebar.date_input("Inizio", min(all_dates).date())
            end_d = st.sidebar.date_input("Fine", max(all_dates).date())
            mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
            df_plot = df_port[mask].copy()

            for n in selected_names:
                df_plot[n] = df_plot[n + '_pnl'].cumsum()
            
            df_plot['TOTALE'] = df_plot[selected_names].sum(axis=1)
            df_plot['DD'] = df_plot['TOTALE'] - df_plot['TOTALE'].cummax()

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['TOTALE'], name='TOTAL', line=dict(color='black', width=3)), row=1, col=1)
            for n in selected_names:
                fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[n], name=n, line=dict(width=1), opacity=0.3), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['DD'], name='Drawdown', fill='tozeroy', line=dict(color='red')), row=2, col=1)
            
            fig.update_layout(plot_bgcolor='white', height=750, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # Tabella Performance
            st.write("### 📊 Risultati Annuali & ROE Live")
            df_plot['Year'] = df_plot['date'].dt.year
            res = df_plot.groupby('Year')[[n + '_pnl' for n in selected_names]].sum().round(0)
            res['TOTALE PnL'] = res.sum(axis=1)
            if margine_totale > 0:
                res['ROE % (su Margine Live)'] = (res['TOTALE PnL'] / margine_totale * 100).round(2)
            
            st.dataframe(res.style.format("{:,.2f}"), use_container_width=True)
