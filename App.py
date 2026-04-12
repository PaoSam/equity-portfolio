import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime

st.set_page_config(page_title="Titan Portfolio Professional", layout="wide")

st.markdown("# 📈 Analisi Avanzata Portafoglio Titan")

uploaded_files = st.file_uploader("Carica file Titan (.txt)", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = []
    strumenti_caricati = set()
   
    def load_equity(uploaded_file):
        try:
            content = uploaded_file.getvalue().decode("utf-8")
            data = []
            for line in content.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3:
                    data.append({
                        'date': datetime.strptime(parts[0], '%d/%m/%Y'),
                        'pnl': float(parts[1]),
                        'pos': int(float(parts[2]))
                    })
            return pd.DataFrame(data).sort_values('date')
        except: 
            return None

    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        ticker = name.split('_')[0].upper().strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())
            strumenti_caricati.add(ticker)

    if raw_data:
        selected_names = []
        ticker_map = {}
       
        # --- SIDEBAR ---
        st.sidebar.header("🗓️ Filtri Temporali")
        abs_min_date, abs_max_date = min(all_dates).date(), max(all_dates).date()
        start_date = st.sidebar.date_input("Data Inizio", value=abs_min_date, min_value=abs_min_date, max_value=abs_max_date)
        end_date = st.sidebar.date_input("Data Fine", value=abs_max_date, min_value=abs_min_date, max_value=abs_max_date)
        
        st.sidebar.write("---")
        st.sidebar.header("🎲 Parametri Monte Carlo")
        n_sim = st.sidebar.slider("Numero Simulazioni", 100, 5000, 1000)
        n_giorni = st.sidebar.number_input("Giorni Proiezione", value=252)
        
        st.sidebar.write("---")
        st.sidebar.header("🛠️ Strategie")
        for name in sorted(raw_data.keys()):
            ticker_map[name] = name.split('_')[0].upper().strip()
            if st.sidebar.checkbox(f"{name}", value=True, key=name):
                selected_names.append(name)

        st.sidebar.write("---")
        show_total_equity = st.sidebar.checkbox("Mostra Equity Totale (Portafoglio)", value=True, key="show_total")

        # ====================== NUOVA TABELLA MARGINI MANUALI ======================
        st.sidebar.write("---")
        st.sidebar.subheader("📌 Margini Manuali (editabili)")

        # Inizializza / aggiorna session_state se ci sono nuovi ticker
        if 'manual_margins' not in st.session_state or \
           st.session_state.get('last_tickers') != sorted(strumenti_caricati):
            df_init = pd.DataFrame({
                'Asset': list(strumenti_caricati),
                'Margine ($)': [0.0] * len(strumenti_caricati)
            }).set_index('Asset')
            st.session_state.manual_margins = df_init
            st.session_state.last_tickers = sorted(strumenti_caricati)

        # Tabella editabile
        edited_df = st.sidebar.data_editor(
            st.session_state.manual_margins,
            num_rows="fixed",
            use_container_width=True,
            column_config={
                "Margine ($)": st.column_config.NumberColumn(
                    format="$%d",
                    min_value=0,
                    step=100
                )
            }
        )
        st.session_state.manual_margins = edited_df
        manual_margins_dict = edited_df['Margine ($)'].to_dict()
        # ===========================================================================

        if selected_names:
            dates_set = sorted([d for d in list(set(all_dates)) if start_date <= d.date() <= end_date])
            df_master = pd.DataFrame({'date': dates_set})
           
            stats_list = []
            active_info = {d: [] for d in dates_set}
           
            for name in selected_names:
                ticker = ticker_map[name]
                temp_df = raw_data[name].copy().rename(columns={'pnl': f'pnl_{name}', 'pos': f'pos_{name}'})
                df_master = df_master.merge(temp_df[['date', f'pnl_{name}', f'pos_{name}']], on='date', how='left').fillna(0)
               
                df_master[f'eq_{name}'] = df_master[f'pnl_{name}'].cumsum()
               
                df_strat = temp_df[(temp_df['date'].dt.date >= start_date) & (temp_df['date'].dt.date <= end_date)].copy()
                df_strat['is_active'] = df_strat[f'pos_{name}'] != 0
                df_strat['trade_id'] = (df_strat['is_active'] != df_strat['is_active'].shift()).cumsum()
                trades = df_strat[df_strat['is_active']].groupby('trade_id')[f'pnl_{name}'].sum()
               
                for d in dates_set:
                    pos_val = df_master.loc[df_master['date'] == d, f'pos_{name}'].values[0]
                    if pos_val != 0:
                        active_info[d].append(f"{name}({'L' if pos_val > 0 else 'S'})")
                
                if not trades.empty:
                    wins = trades[trades > 0]
                    losses = trades[trades <= 0]
                    daily_returns = df_strat[f'pnl_{name}']
                    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() != 0 else 0
                    equity_curve = daily_returns.cumsum()
                    max_dd_strat = abs((equity_curve - equity_curve.cummax()).min())
                    days_diff = (end_date - start_date).days
                    cagr = (daily_returns.sum() / days_diff * 365) if days_diff > 0 else 0
                    stats_list.append({
                        "Strategia": name,
                        "Trades": len(trades),
                        "Win Rate": f"{(len(wins)/len(trades)*100):.1f}%",
                        "Profit Factor": round(abs(wins.sum()/losses.sum()), 2) if losses.sum() != 0 else np.inf,
                        "Sharpe": round(sharpe, 2),
                        "MAR": round(cagr/max_dd_strat, 2) if max_dd_strat != 0 else 0,
                        "Avg Trade ($)": round(trades.mean(), 2)
                    })

            # --- GRAFICI PRINCIPALI ---
            pnl_cols = [f'pnl_{n}' for n in selected_names]
            df_master['Equity_Totale'] = df_master[pnl_cols].sum(axis=1).cumsum()
            df_master['DD'] = df_master['Equity_Totale'] - df_master['Equity_Totale'].cummax()
           
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.5, 0.25, 0.25],
                                subplot_titles=("Equity Line Portafoglio", "Drawdown ($)", "Margine Reale ($)"))
           
            if show_total_equity:
                fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Equity_Totale'], 
                                       name='PORTAFOGLIO', line=dict(color='black', width=4.5)), 
                             row=1, col=1)

            colors = px.colors.qualitative.Plotly + px.colors.qualitative.Bold + px.colors.qualitative.Vivid
            for i, name in enumerate(selected_names):
                color = colors[i % len(colors)]
                fig.add_trace(go.Scatter(
                    x=df_master['date'], 
                    y=df_master[f'eq_{name}'], 
                    name=name, 
                    line=dict(color=color, width=2.8),
                    opacity=0.95
                ), row=1, col=1)

            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['DD'], 
                                   name='Drawdown', fill='tozeroy', line=dict(color='red')), 
                         row=2, col=1)

            # --- CALCOLO MARGINE MANUALE + CONTEGGIO STRATEGIE ATTIVE ---
            net_exposure = {d: {t: 0 for t in strumenti_caricati} for d in dates_set}
            active_count_per_day = {d: 0 for d in dates_set}

            for name in selected_names:
                for d in dates_set:
                    pos_val = df_master.loc[df_master['date']==d, f'pos_{name}'].values[0]
                    ticker = ticker_map[name]
                    net_exposure[d][ticker] += pos_val
                    if pos_val != 0:
                        active_count_per_day[d] += 1

            # Margine calcolato SOLO con i valori manuali
            m_giornaliero = [sum(abs(pos) * manual_margins_dict.get(t, 0) for t, pos in net_exposure[d].items()) 
                           for d in dates_set]

            # Hover migliorato
            hover_text = []
            for d in dates_set:
                strat_list = active_info[d]
                count = active_count_per_day[d]
                if count > 0:
                    text = f"<b>{count} strategie attive</b><br>" + "<br>".join(strat_list)
                else:
                    text = "Nessuna strategia attiva"
                hover_text.append(text)

            fig.add_trace(go.Scatter(
                x=df_master['date'], 
                y=m_giornaliero, 
                name='Margine', 
                fill='tozeroy', 
                line=dict(color='orange', width=3),
                text=hover_text,
                hovertemplate="Margine: $%{y:,.0f}<br>%{text}<extra></extra>"
            ), row=3, col=1)

            fig.update_layout(height=900, template="plotly_white", hovermode="x unified", showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

            # --- Il resto del codice (correlazione, statistiche, Monte Carlo, ROE, ecc.) rimane IDENTICO ---
            st.write("---")
            st.write("### 🧬 Matrice di Correlazione")
            corr = df_master[pnl_cols].corr()
            corr.columns = [c.replace('pnl_', '') for c in corr.columns]
            corr.index = [c.replace('pnl_', '') for c in corr.index]
            fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r', zmin=-1, zmax=1)
            fig_corr.update_layout(height=700)
            st.plotly_chart(fig_corr, use_container_width=True)

            st.write("---")
            col1, col2 = st.columns([2, 1])
            with col1:
                st.write("### 📊 Performance Trade")
                st.dataframe(pd.DataFrame(stats_list), use_container_width=True, hide_index=True)
            with col2:
                total_pnl = df_master[pnl_cols].sum().sum()
                total_dd = abs(df_master['DD'].min())
                days_diff_total = (end_date - start_date).days
                ann_return = (total_pnl / days_diff_total * 365) if days_diff_total > 0 else 0
                st.write("### 🏆 Portfolio Efficiency")
                st.metric("MAR Ratio Totale", f"{(ann_return/total_dd if total_dd!=0 else 0):.2f}")
                st.metric("Rendimento Annuo Medio", f"${ann_return:,.0f}")

            st.write("---")
            st.write(f"### 🎲 Simulazione Monte Carlo ({n_sim} percorsi)")
            returns = df_master['Equity_Totale'].diff().dropna()
            if not returns.empty:
                mu = returns.mean()
                sigma = returns.std()
                ultimo_valore = df_master['Equity_Totale'].iloc[-1]
                simulazioni = np.zeros((n_giorni, n_sim))
                for i in range(n_sim):
                    cambiamenti = np.random.normal(mu, sigma, n_giorni)
                    simulazioni[:, i] = ultimo_valore + np.cumsum(cambiamenti)
                media_sim = np.mean(simulazioni, axis=1)
                p5 = np.percentile(simulazioni, 5, axis=1)
                p95 = np.percentile(simulazioni, 95, axis=1)
                x_axis = np.arange(n_giorni)
                fig_mc = go.Figure()
                fig_mc.add_trace(go.Scatter(
                    x=np.concatenate([x_axis, x_axis[::-1]]),
                    y=np.concatenate([p95, p5[::-1]]),
                    fill='toself',
                    fillcolor='rgba(0, 100, 255, 0.1)',
                    line=dict(color='rgba(255,255,255,0)'),
                    hoverinfo="skip",
                    name='Confidenza 90%'
                ))
                for i in range(min(n_sim, 50)):
                    fig_mc.add_trace(go.Scatter(
                        x=x_axis, y=simulazioni[:, i], mode='lines',
                        line=dict(color='rgba(100, 100, 100, 0.3)', width=1),
                        showlegend=False
                    ))
                fig_mc.add_trace(go.Scatter(x=x_axis, y=media_sim, name='Media Attesa', line=dict(color='blue', width=3)))
                fig_mc.add_trace(go.Scatter(x=x_axis, y=p5, name='Pessimista (5%)', line=dict(color='red', width=2, dash='dash')))
                fig_mc.add_trace(go.Scatter(x=x_axis, y=p95, name='Ottimista (95%)', line=dict(color='green', width=2, dash='dash')))
                fig_mc.update_layout(height=600, template="plotly_white", xaxis_title="Giorni Futuri", yaxis_title="Proiezione Equity ($)")
                st.plotly_chart(fig_mc, use_container_width=True)
                st.success(f"Basato sui rendimenti storici: c'è il 95% di probabilità che l'equity sia superiore a **${p5[-1]:,.0f}** tra {n_giorni} giorni.")

            st.write("---")
            st.write("### 📅 Performance Annuale e ROE")
            df_master['Year'] = df_master['date'].dt.year
            res = df_master.groupby('Year')[pnl_cols].sum().round(0)
            res['PnL Totale'] = res.sum(axis=1)
            max_m, max_dd = max(m_giornaliero), abs(df_master['DD'].min())
            cap_pru = max_m + (max_dd * 1.5)
            res['ROE %'] = (res['PnL Totale'] / cap_pru * 100).round(2)
            st.dataframe(res.style.format("{:,.0f}"), use_container_width=True)

            st.sidebar.write("---")
            st.sidebar.metric("Picco Margine Reale", f"${max_m:,.0f}")
            st.sidebar.metric("Max Drawdown", f"-${max_dd:,.0f}")
            st.sidebar.info(f"**Capitale Prudenziale:**\n${cap_pru:,.0f}")
