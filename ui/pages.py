import streamlit as st

dashboard = st.Page("ui/ui_pages/dashboard.py", title="Dashboard", url_path="dashboard")
new_sermon = st.Page("ui/ui_pages/new_sermon_enhanced.py", title="New Sermon")
batch_update = st.Page("ui/ui_pages/batch_update.py", title="Batch Update")
validation = st.Page("ui/ui_pages/validation.py", title="Validation")
jobs = st.Page("ui/ui_pages/jobs.py", title="Jobs")
sermon_import = st.Page("ui/ui_pages/sermon_import.py", title="Import Sermons")
library = st.Page("ui/ui_pages/library.py", title="Library")
analytics = st.Page("ui/ui_pages/analytics.py", title="Analytics")
settings = st.Page("ui/ui_pages/settings.py", title="Settings")
