app_name = "recruitment"
app_title = "Recruitment"
app_publisher = "Mantra"
app_description = "Recruitment"
app_email = "info@mantratec.com"
app_license = "mit"

# include js in doctype views
doctype_js = {
   
    "Job Offer":"public/js/job_offer.js",
    "Job Requisition":"public/js/job_requisition.js",
    "Job Applicant":"public/js/job_applicant.js",
    "Job Opening":"public/js/job_opening.js",
    "Interview":"public/js/interview.js",
}

app_include_js = [
    "/assets/recruitment/js/attach.js",
    ]


# doctype_js=  {"Sales Invoice" : "public/js/sales_invoice.js"}

# doctype_tree_js = {
    # "doctype" : "public/js/doctype_tree.js"
# }
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "recruitment/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "recruitment.utils.jinja_methods",
# 	"filters": "recruitment.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "recruitment.install.before_install"
# after_install = "recruitment.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "recruitment.uninstall.before_uninstall"
# after_uninstall = "recruitment.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "recruitment.utils.before_app_install"
# after_app_install = "recruitment.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "recruitment.utils.before_app_uninstall"
# after_app_uninstall = "recruitment.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "recruitment.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

permission_query_conditions = {
    "Job Opening": "recruitment.permission.permission.permission_query_condition",
    "Job Applicant": "recruitment.permission.permission.permission_query_condition",
    "Job Requisition": "recruitment.permission.permission.permission_query_condition",
    "Job Offer": "recruitment.permission.permission.permission_query_condition",
    "Interview": "recruitment.permission.permission.permission_query_condition"
}

has_permission = {
    "Job Opening": "recruitment.permission.permission.has_permission",
    "Job Applicant": "recruitment.permission.permission.has_permission",
    "Job Requisition": "recruitment.permission.permission.has_permission",
    "Job Offer": "recruitment.permission.permission.has_permission",
    "Interview": "recruitment.permission.permission.has_permission",
}


override_doctype_class = {
    "Interview": "recruitment.overrides.interview.CustomInterview",
    "Job Requisition": "recruitment.overrides.job_requisition.CustomJobRequisition"
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Job Applicant":{
        "after_insert":"recruitment.backend_code.job_applicant.job_applicant.send_job_description_to_applicant",
         "validate":"recruitment.backend_code.job_applicant.job_applicant.validate_duplicates_for_job_applicant"
    },
    "Job Opening":{
        "validate":"recruitment.backend_code.job_applicant.job_applicant.validate_duplicates_for_job_opening",
    },
  
    "Job Offer":{
        "on_submit":"recruitment.backend_code.job_offer.job_offer.job_applicant_update_status",
        "on_update_after_submit":"recruitment.backend_code.job_offer.job_offer.job_applicant_update_status_after_approve",
    },
    "Interview Feedback":{
        "on_submit":"recruitment.backend_code.interview.interview.send_interview_feedback_notification",
    },
  
}

# Scheduled Tasks
# ---------------

scheduler_events = {

    "cron": {
        "07 17 * * *":[
            "recruitment.backend_code.job_offer.job_offer.send_joining_reminders"
        ],
        "*/10 * * * *":[
            "recruitment.backend_code.job_applicant.job_applicant.send_scheduled_emails"
        ],
        "*/59 * * * *":[
            "recruitment.backend_code.job_offer.job_offer.send_scheduled_emails_for_job_offer"
        ],
        "45 9 * * *":[
            "recruitment.recruitment.doctype.recruitment_setting.recruitment_setting.send_open_status_email"
        ],
        "0 22 * * *":[
            "recruitment.backend_code.job_applicant.job_applicant.send_daily_report",
            "recruitment.backend_code.job_applicant.job_applicant.check_and_send_monthly_report"
        ]

        
    },
	"daily": [
        "recruitment.overrides.interview.send_feedback_reminder"
	],
}



#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "recruitment.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["recruitment.utils.before_request"]
# after_request = ["recruitment.utils.after_request"]

# Job Events
# ----------
# before_job = ["recruitment.utils.before_job"]
# after_job = ["recruitment.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"recruitment.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
    {"dt": "Workflow", "filters": [["name", "in", ["Job Offer","Job Requisition","Job Applicant Workflow"]]]},
     {"dt": "Workflow State", "filters": [["name", "in", ["Send to Team Leader","Approval Pending By Director","Approval Pending By Team Lead- Talent Acquisition","On Hold","Offer Accepted","Offer Declined","Approval Pending By Manager Talent Acquisition"]]]},
     {"dt": "Workflow Action Master", "filters": [["name", "in", ["Send to Team Leader","Resubmit","Offer Accept","Offer Decline"]]]},
      {"dt": "Workspace", "filters": [["name", "in", ["TA User","TA Manager","TL User","Hiring Manager"]]]},
   
    {"dt": "Email Template", "filters": [["name", "in", ["Submission of Resignation Email & Acceptance Letter","Document Submission Required for Further Process","Job Description Option for candidate","Interview Feedback Selected","Interview Feedback On Hold","Interview Feedback Rejection","Job Applicant is Rejected","Job Applicant is Rejected","Job Applicant Shortlisted","Job Requisition Approved","Job Requisition Approved"]]]},
]


