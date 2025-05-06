__version__ = "0.0.1"


import frappe.email.doctype.email_queue.email_queue as email_queue
import recruitment.backend_code.job_requisition.job_requisition as job_requisition

email_queue.EmailQueue.send = job_requisition.send
email_queue.SendMailContext.build_message = job_requisition.build_message