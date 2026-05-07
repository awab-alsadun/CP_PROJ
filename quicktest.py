from app.services.query_service import _is_sql_query

print(_is_sql_query("how many overdue invoices"))  # True
print(_is_sql_query("which invoices mention server rack"))  # False
print(_is_sql_query("total spent on vendor ABC"))  # True