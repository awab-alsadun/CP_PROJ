# cleanup_orphan_storage.py
# Run from backend/ with venv active
import os
from app.core.supabase import get_supabase

COMPANY_ID = "7bf697fc-7220-40c7-9678-542d624d22ad"
BUCKET = "invoices"

sb = get_supabase()

# Get all storage_paths currently referenced in DB
result = sb.table("invoice_raw_documents").select("storage_path").not_.is_("storage_path", "null").execute()
valid_paths = {row["storage_path"] for row in result.data}
print(f"Valid paths in DB: {len(valid_paths)}")

# List all files in the bucket under this company folder
all_files = []
offset = 0
limit = 100
while True:
    page = sb.storage.from_(BUCKET).list(COMPANY_ID, {"limit": limit, "offset": offset})
    if not page:
        break
    all_files.extend(page)
    if len(page) < limit:
        break
    offset += limit
files = all_files
print(f"Files in bucket: {len(files)}")

# Identify orphans
orphans = []
for f in files:
    full_path = f"{COMPANY_ID}/{f['name']}"
    if full_path not in valid_paths:
        orphans.append(full_path)

print(f"Orphans to delete: {len(orphans)}")
for p in orphans[:5]:
    print(f"  {p}")

confirm = input("Delete these? (yes/no): ")
if confirm == "yes":
    # Supabase remove() takes a list of paths
    sb.storage.from_(BUCKET).remove(orphans)
    print(f"Deleted {len(orphans)} orphans.")