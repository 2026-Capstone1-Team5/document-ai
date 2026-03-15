# Architecture

## Parsing Pipeline

```mermaid
flowchart LR
    PDF[Input PDF] --> Check{Text layer looks suspicious?}
    Check -- No --> Normal[Run MinerU on original PDF]
    Check -- Yes --> Rasterize[Rasterize pages to image only PDF]
    Rasterize --> OCRPath[Run MinerU on rasterized PDF]
    Normal --> Output[Markdown]
    OCRPath --> Output
```

## Examples

![Original receipt](benchmark/results/receipt_original.png)

| MinerU | Ours |
| --- | --- |
| Serv^ Marina   <br>2024-09-14 09:52:38   <br>[ا   <br>ĩable: 15 Commande#: 73 Siege#: 1   <br>#Clients: 1<br><br>1 JUS ORANGE REGULER 4.85 FP  <br>1 SPECIAE CORA 19.85 FP<br><br>SOUS-TOTAL<br><br>24.70<br><br>TPS: 747755411RT0001  <br>TVQ: 1230653153TQ0001  <br>TPS: 1.24  <br>TVQ; 2.45  <br>TOTAL: 28.40<br><br>FACTURE ORIGINALE<br><br>Visitez chezcora.com/cartefidelite pour connaetre votre solde. Visit chezcora.com/loya1tycard to check your balance. | Serv: Marina   <br>2024-09-14 09:52:38   <br>FACTURE #7-93-1   <br>Table: 15 Commande#: 73 Siege#: 1   <br>#Clients: 1   <br>1 JUS ORANGE REGULIER 4.85 FP   <br>1 SPECIAL CORA 19.85 FP<br><br>SOUS-TOTAL<br><br>24.70<br><br>TPS: 747755411RT0001  <br>TVQ: 1230663153TQ0001  <br>TPS: 1.24  <br>TVQ: 2.46  <br>TOTAL: 28.40<br><br>FACTURE ORIGINALE<br><br>2024-09-14 09:52:38   <br>05GC-04B1-04A6-00FV   <br>6010-5858-1705<br><br>Visitez chezcora.com/cartefidelite pour connaetre votre solde. Visit chezcora.com/loyaltycard to check your balance. |
