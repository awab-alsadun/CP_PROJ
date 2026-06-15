import json
data = json.load(open('sample_data/dataset.json'))
bad = [p['invoice_number'] for p in data['payables'] + data['receivables']
       if p['due_date'] is None and not p['invoice_number'].endswith('67')]
print(bad if bad else 'CLEAN')