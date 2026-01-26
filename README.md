# Equity Portfolio Analysis

# 📈 Titan Portfolio Professional

Analisi avanzata e gestione del rischio per portafogli di trading basati su strategie **Titan**. Questa web app permette di aggregare più flussi di dati, monitorare i margini in tempo reale e proiettare le performance future tramite simulazioni statistiche.

🚀 **Prova l'app live qui:** https://equity-portfolio-paolosamarelli.streamlit.app/

---

## 🛠️ Funzionalità Principali

### 1. 📊 Analisi di Portafoglio Aggregata
* **Multi-Upload**: Caricamento simultaneo di file `.txt` esportati da Titan.
* **Equity Line Master**: Visualizzazione della performance combinata di tutte le strategie selezionate.
* **Drawdown Real-Time**: Monitoraggio costante del rischio monetario storico e attuale.

### 2. 🛡️ Gestione del Rischio e Margini
* **Live IBKR Margins**: Recupero automatico dei margini iniziali tramite web scraping dai server di Interactive Brokers.
* **Margine Reale Giornaliero**: Calcolo dell'occupazione di capitale basato sulle posizioni (Long/Short) effettivamente aperte.
* **Capitale Prudenziale**: Calcolo del capitale suggerito per operare in sicurezza basato sulla formula:  
  `Capitale = Margine Max + (Max Drawdown * 1.5)`

### 3. 🧬 Correlazione e Statistiche
* **Heatmap di Correlazione**: Identificazione delle dipendenze tra le strategie per migliorare la diversificazione.
* **KPI Professionali**: Sharpe Ratio, MAR Ratio, Profit Factor e Win Rate per ogni singola strategia.
* **ROE Anno su Anno**: Calcolo del ritorno sul capitale basato sul capitale prudenziale.

### 4. 🎲 Simulazione Monte Carlo
* **Proiezione 252 giorni**: Generazione di migliaia di scenari futuri basati sulla volatilità e media storica dei rendimenti.
* **Cono di Probabilità**: Visualizzazione dell'area di confidenza (95%) per stimare lo scenario peggiore e migliore a un anno.

Da aggiungere proposta di Simone
consentire di introdurre il calcolo di slippage/commissioniconsentire di configurare il numero di contratti per una strategiaconsentire di usare un moltiplicatore per una strategia, ad esempio se la strategia gira su GC ma la si trada con MGC (il moltiplicatore in questo caso sarebbe 0.1)


