import pandas as pd
import sys
filename = sys.argv[1]

# Load your CSV file
if len(sys.argv) < 2:
    print("Please provide a CSV filename.")
    sys.exit(1)

df = pd.read_csv(filename +'/WFT0000.csv')

# Filter out rows where 'column_name' is 0
df_cleaned = df[df['Fx_N'] != 0]

# Save the cleaned data to a new CSV file
df_cleaned.to_csv(filename + '/cleaned_file.csv', index=False)