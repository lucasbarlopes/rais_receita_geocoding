import os
import pandas as pd

# Pasta onde estão os arquivos Parquet
folder_path = r"D:\Arq-Azzoni\UrbanSprawl\Bases_dados\RAIS_estab\temp_geocoding\parquet_py"
excel_path = r"D:\Arq-Azzoni\UrbanSprawl\Bases_dados\RAIS_estab\temp_geocoding\parquet_py\amostra_sp_2002_2023.xlsx"

amostras = []

# Loop do ano 2002 até 2023
for ano in range(2002, 2024):
    file_name = f"sp_{ano}.parquet"
    file_path = os.path.join(folder_path, file_name)
    
    if os.path.exists(file_path):
        print(f"Lendo {file_name}...")
        df = pd.read_parquet(file_path)
        
        # Adiciona a coluna 'ano' caso ela não exista no arquivo
        if 'ano' not in df.columns and 'ANO' not in df.columns:
            df['ano'] = ano
            
        # Pega 500 registros aleatórios (ou o total se houver menos de 500 linhas)
        n_amostra = min(500, len(df))
        df_amostra = df.sample(n=n_amostra, random_state=42)
        
        amostras.append(df_amostra)
    else:
        print(f"Aviso: Arquivo {file_name} não encontrado.")

# Junta as amostras de todos os anos e exporta para Excel
if amostras:
    df_final = pd.concat(amostras, ignore_index=True)
    df_final.to_excel(excel_path, index=False)
    print(f"\nSucesso! Amostra total com {len(df_final)} linhas gerada em:\n{excel_path}")
else:
    print("Nenhum arquivo foi localizado.")