# =============================================
# PROGRAMMA UNICO: Caricamento + Grafico interattivo con checkbox
# — PnL netto anno per anno (NON cumulativo, solo movimenti dell’anno)
# — Equity_Totale PnL = somma PnL anno corrente di tutte le strategie
# =============================================

import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import glob
import os
import ipywidgets as widgets
from ipywidgets import interact, interactive, Output, VBox, Checkbox, DatePicker, Button, HBox
from IPython.display import display, clear_output, Markdown
from google.colab import files

# Colori per le linee
COLORS = ['cyan', 'orange', 'lime', 'magenta', 'yellow', 'pink', 'lightblue', 'purple']

# =============================================
def load_equity(file_path):
    data = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 6:
                    try:
                        date = datetime.strptime(parts[0], '%d/%m/%Y')
                        pnl = float(parts[1])
                        data.append({'date': date, 'pnl': pnl})
                    except:
                        continue
    except Exception as e:
        print(f"Errore lettura {file_path}: {e}")
        return None

    if not data:
        return None

    df = pd.DataFrame(data)
    # Raggruppiamo per data per gestire eventuali trade multipli nello stesso giorno
    df = df.groupby('date')['pnl'].sum().reset_index()
    df = df.sort_values('date')
    # Creiamo l'equity cumulativa per il grafico
    df['equity'] = df['pnl'].cumsum()
    return df[['date', 'equity', 'pnl']]

# =============================================
display(Markdown("### Equity Portfolio Interattivo – Paolo"))

main_output = Output()

def clear_old_txt_files():
    for f in glob.glob("*.txt"):
        try:
            os.remove(f)
        except:
            pass

def process_and_show():
    with main_output:
        clear_output(wait=True)

        txt_files = sorted(glob.glob("*.txt"))

        if not txt_files:
            display(Markdown("**Nessun file TXT presente.** Caricali con il bottone qui sotto."))
            return

        display(Markdown(f"**Trovati {len(txt_files)} file TXT:**"))
        for f in txt_files:
            display(Markdown(f"- {f}"))

        equity_dfs = {}
        all_dates = set()

        for fname in txt_files:
            df = load_equity(fname)
            if df is not None:
                equity_dfs[fname] = df
                all_dates.update(df['date'])

        if not equity_dfs:
            display(Markdown("**Nessun dato valido estratto dai file.**"))
            return

        # Creiamo un dataframe con tutte le date
        df_port = pd.DataFrame({'date': sorted(list(all_dates))})

        equity_columns = []
        pnl_columns = []
        for name, df in equity_dfs.items():
            col_name = name.replace('.txt', '').replace('#', '').strip()
            # Merge dell'equity (per grafici) e del pnl (per tabella annuale)
            df_port = df_port.merge(df.rename(columns={'equity': col_name, 'pnl': col_name + '_pnl'}),
                                    on='date', how='left')
            equity_columns.append(col_name)
            pnl_columns.append(col_name + '_pnl')

        # Riempire i buchi: l'equity resta costante (ffill), il pnl giornaliero è 0 se non ci sono trade
        for p_col in pnl_columns:
            df_port[p_col] = df_port[p_col].fillna(0)
        df_port[equity_columns] = df_port[equity_columns].ffill().fillna(0)

        # ────────────────────────────────────────────────
        # CALCOLO PnL ANNUALE (SOLO MOVIMENTI DELL'ANNO)
        # ────────────────────────────────────────────────
        df_port['Year'] = df_port['date'].dt.year
        years = sorted(df_port['Year'].unique())

        annual_pnl = pd.DataFrame(index=years)

        for col in equity_columns:
            pnl_col_name = col + '_pnl'
            # Somma dei pnl giornalieri dell'anno specifico
            yearly_pnl = df_port.groupby('Year')[pnl_col_name].sum().round(0).astype(int)
            annual_pnl[col + ' PnL'] = yearly_pnl

        # Calcolo Equity Totale: Somma orizzontale dei PnL annuali delle singole strategie
        annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)

        # Aggiunta riga Totale Storico (Somma di tutte le righe)
        totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
        annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

        # ────────────────────────────────────────────────
        # Tabella PnL annuale
        # ────────────────────────────────────────────────
        display(Markdown("### PnL netto prodotto anno per anno (non cumulativo)"))
        display(Markdown("*Solo i movimenti di quell’anno – Equity_Totale PnL = somma PnL anno corrente*"))

        def highlight_total_row(row):
            if row.name == 'TOTALE STORICO':
                return ['background-color: #d1e7dd; font-weight: bold'] * len(row)
            return [''] * len(row)

        styled = annual_pnl_with_total.style\
            .format('{:,.0f}', na_rep='—')\
            .apply(highlight_total_row, axis=1)\
            .set_properties(**{'text-align': 'center'})\
            .set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])

        display(styled)

        # ────────────────────────────────────────────────
        # Grafico equity + drawdown
        # ────────────────────────────────────────────────
        start_picker = DatePicker(description='Inizio:', value=df_port['date'].min().date())
        end_picker   = DatePicker(description='Fine:',   value=df_port['date'].max().date())

        checkboxes = {col: Checkbox(value=True, description=col, indent=False) for col in equity_columns}
        total_checkbox = Checkbox(value=True, description='Equity Totale', indent=False)

        output_plot = Output()

        def update_plot(start, end, **kwargs):
            with output_plot:
                clear_output(wait=True)

                if not start or not end or start > end:
                    print("Seleziona date valide")
                    return

                start_dt = pd.to_datetime(start)
                end_dt   = pd.to_datetime(end)

                df_plot = df_port[(df_port['date'] >= start_dt) & (df_port['date'] <= end_dt)].copy()

                if df_plot.empty:
                    print("Nessun dato nel periodo")
                    return

                # Normalizzazione grafico (parte da 0 nel periodo selezionato)
                visible_cols = [col for col in equity_columns if checkboxes[col].value]

                for col in visible_cols:
                    initial_val = df_plot[col].iloc[0]
                    df_plot[col] = df_plot[col] - initial_val

                df_plot['Equity_Totale_Dynamic'] = df_plot[visible_cols].sum(axis=1)

                gain_dollari = df_plot['Equity_Totale_Dynamic'].iloc[-1]
                gain_str = f"Gain periodo selezionato: {'+' if gain_dollari >= 0 else ''}{gain_dollari:,.0f} $"

                # Drawdown
                df_plot['Peak'] = df_plot['Equity_Totale_Dynamic'].cummax()
                df_plot['Drawdown'] = df_plot['Equity_Totale_Dynamic'] - df_plot['Peak']

                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 11), sharex=True,
                                                gridspec_kw={'height_ratios': [3, 1]})

                fig.suptitle(gain_str, fontsize=14, fontweight='bold', y=0.98)

                for i, col in enumerate(visible_cols):
                    ax1.plot(df_plot['date'], df_plot[col], label=col, color=COLORS[i % len(COLORS)], lw=1.3)

                if total_checkbox.value:
                    ax1.plot(df_plot['date'], df_plot['Equity_Totale_Dynamic'], label='Equity Totale', color='black', lw=3.5)

                ax1.set_ylabel('Equity ($)')
                ax1.grid(True, ls='--', alpha=0.5)
                ax1.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9.5)

                ax2.plot(df_plot['date'], df_plot['Drawdown'], color='red', lw=1.8)
                ax2.fill_between(df_plot['date'], df_plot['Drawdown'], 0, color='red', alpha=0.1)
                ax2.set_ylabel('Drawdown', color='red')
                ax2.grid(True, ls='--', alpha=0.5)

                ax2.set_xlabel('Data')
                fig.autofmt_xdate()
                plt.tight_layout(rect=[0, 0, 1, 0.95])
                plt.show()

        interact_args = {'start': start_picker, 'end': end_picker}
        interact_args.update(checkboxes)
        interact_args['total'] = total_checkbox

        interactive_plot = interactive(update_plot, **interact_args)

        controls = VBox([
            HBox([start_picker, end_picker]),
            widgets.Label("Seleziona strategie da includere nel calcolo totale:"),
            HBox([total_checkbox] + list(checkboxes.values()), layout=widgets.Layout(flex_wrap='wrap')),
            output_plot
        ])

        display(controls)
        update_plot(start_picker.value, end_picker.value)

# =============================================
load_button = Button(description="Cancella vecchi + Carica nuovi TXT", button_style='success', layout={'width': '300px'})
output_load = Output()

def on_load(b):
    with output_load:
        clear_output()
        print("→ Eliminazione vecchi TXT...")
        clear_old_txt_files()
        print("→ Caricamento...")
        uploaded = files.upload()
        if uploaded:
            process_and_show()
        else:
            print("Nessun file selezionato.")

load_button.on_click(on_load)

# Iniziale
with main_output:
    clear_output()
    display(Markdown("### Benvenuto! Carica i file TXT per generare l'analisi."))

display(VBox([load_button, output_load, main_output]))
