import streamlit as st

dashboard = st.Page("ui/ui_pages/dashboard.py", title="Dashboard", icon="📊")
new_sermon = st.Page("ui/ui_pages/new_sermon_enhanced.py", title="New Sermon", icon="🎵")
batch_update = st.Page("ui/ui_pages/batch_update.py", title="Batch Update", icon="🔄")
validation = st.Page("ui/ui_pages/validation.py", title="Validation", icon="✅")
jobs = st.Page("ui/ui_pages/jobs.py", title="Jobs", icon="⚙️")
library = st.Page("ui/ui_pages/library.py", title="Library", icon="📚")
analytics = st.Page("ui/ui_pages/analytics.py", title="Analytics", icon="📈")
config_management = st.Page("ui/ui_pages/config_management.py", title="Config Management", icon="🔧")
settings = st.Page("ui/ui_pages/settings.py", title="Settings", icon="⚙️")
