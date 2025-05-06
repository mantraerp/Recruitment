import frappe
from frappe import _
from frappe.utils.user import get_users_with_role
from frappe.email.doctype.email_queue.email_queue import SendMailContext
from frappe.email.smtp import SMTPServer
from frappe.utils import get_hook_method


@frappe.whitelist()
def handle_workflow_action(doc_name, action, reason=None):
    """
    Handles workflow actions for Job Requisition, including sending emails using templates.

    Args:
        doc_name (str): Name of the Job Requisition document.
        action (str): Action performed in the workflow ("approve" or "reject").
        reason (str, optional): Reason for rejection (if applicable).
    """
    try:
        # Fetch the Job Requisition document
        doc = frappe.get_doc("Job Requisition", doc_name)
        template_name = None
        # Get recipient details

        # Define the template name based on the action
        if action == "approve":
            template_name = "Job Requisition Approved"
            context = {
                "employee_name": frappe.db.get_value("User", doc.owner, "full_name"),
                "doc": doc,
            }
            sender = frappe.db.get_value(
                    "Email Account", doc.custom_requisition_approver, "email_id")
        elif action == "pending director approval":
            subject = "Job Requisition Approval"
            context = {
                "director_name": frappe.db.get_value(
                    "User", doc.custom_requisition_approver, "full_name"
                ),
                "doc": doc,
            }
            sender = frappe.db.get_value("Email Account",{"email_id":doc.owner}, "email_id")
            
            message = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; color: #333; }}
                    .header {{ font-size: 18px; font-weight: bold;}}
                    .content {{ margin-top: 20px; }}
                    .footer {{ margin-top: 30px; font-size: 12px; color: #888; }}
                </style>
            </head>
            <body>
                <div class="header">Job Requisition Approval</div>
                <div class="content">
                    <p>Dear {frappe.db.get_value("User",doc.custom_requisition_approver,'full_name')},</p>
                    <p>A new job requisition has been submitted and requires your approval. Below are the details:</p>
                    <ul>
                        <li><strong>Job Title:</strong> {doc.designation}</li>
                        <li><strong>Department:</strong> {doc.department}</li>
                        <li><strong>Requested By:</strong> {doc.requested_by_name}</li>
                        <li><strong>Requisition ID:</strong> {doc.name}</li>
                    </ul>
                    <p>Please click the link below to approve or reject the request:</p>
                    <p><a href="{frappe.utils.get_url_to_form(doc.doctype, doc.name)}">View Job Requisition</a></p>
                    <p>Thank you for your prompt attention.</p>
                </div>
                <div class="footer">
                    <p>Best regards,</p>
                    <p>{doc.company} Team</p>
                </div>
            </body>
            </html>
            """
        elif action == "reject":
            template_name = "Job Requisition Rejected"
            sender = frappe.db.get_value(
                    "Email Account", {"email_id":doc.custom_requisition_approver}, "email_id"
                )
              
            context = {
                "employee_name": frappe.db.get_value("User", doc.owner, "full_name"),
                "doc": doc,
                "reason": reason,
            }
            # Save the rejection reason in the document
            doc.custom_rejected_reason = reason
            doc.save()

        # Send the email
        frappe.sendmail(
            recipients=[doc.owner,doc.owner] if action != "pending director approval" else [doc.custom_requisition_approver,doc.owner],
            subject=subject if action == "pending director approval" else frappe.render_template(frappe.get_doc("Email Template", template_name).subject, context),
            cc=get_users_with_role("Manager - Talent Acquisition")+ get_users_with_role("Team Lead - Talent Acquisition"),
            expose_recipients="header",
            message=message if action == "pending director approval" else frappe.render_template(frappe.get_doc("Email Template", template_name).response, context),
            reference_doctype="Job Requisition",
            reference_name=doc_name,
            now=True,
        )
    except Exception as e:
        # Log the error and show a user-friendly message
        frappe.log_error(
            f"Error handling workflow action: {str(e)}", "Workflow Action Error"
        )
        frappe.throw("Unable to process the workflow action. Please check the logs.")


@frappe.whitelist()
def get_hiring_managers(doctype, txt, searchfield, start, page_len, filters):
    department = filters.get("department")

    return frappe.db.sql(
        """
        SELECT user_id FROM `tabEmployee`
        WHERE department = %(department)s
        AND user_id IS NOT NULL
        AND user_id IN (
            SELECT parent FROM `tabHas Role` WHERE role = 'HR Manager'
        )
    """,
        {"department": department},
    )


@frappe.whitelist()
def get_head_of_department(doctype, txt, searchfield, start, page_len, filters):
    department = filters.get("department")

    return frappe.db.sql(
        """
        SELECT user_id FROM `tabEmployee`
        WHERE department = %(department)s
        AND user_id IS NOT NULL
        AND user_id IN (
            SELECT parent FROM `tabHas Role` WHERE role = 'HR Manager' and role = 'Head of Department'
        )
    """,
        {"department": department},
    )


def validate_duplicates(doc, method=None):
    duplicate = frappe.db.exists(
        "Job Opening",
        {
            "designation": doc.designation,
            "department": doc.department,
            "name": ("!=", doc.name),
            "custom_requisition_type": doc.custom_requisition_type,
            "custom_hiring_company": doc.custom_hiring_company,
        },
    )

    if duplicate:
        frappe.throw(
            _(
                "A Job Opening for {0} with Hiring Company {1} in Department {2} already exists"
            ).format(
                frappe.bold(doc.designation),
                frappe.bold(doc.custom_hiring_company),
                frappe.bold(doc.department),
            ),
            title=_("Duplicate Job Opening"),
        )


def send(self, smtp_server_instance: SMTPServer = None):
    """Send emails to recipients."""
    if not self.can_send_now():
        return

    with SendMailContext(self, smtp_server_instance) as ctx:
        ctx.fetch_smtp_server()
        message = None
        recipient_list = []
        for recipient in self.recipients:
            if recipient.is_mail_sent():
                continue
            ctx.update_recipient_status_to_sent(recipient)
            recipient_list.append(recipient.recipient)

            message = ctx.build_message(recipient_list)
        if method := get_hook_method("override_email_send"):
            method(self, self.sender, recipient_list, message)
        else:
            if not frappe.flags.in_test or frappe.flags.testing_email:
                ctx.smtp_server.session.sendmail(
                    from_addr=self.sender,
                    to_addrs=recipient_list,
                    msg=message.decode("utf-8").encode(),
                )

        if frappe.flags.in_test and not frappe.flags.testing_email:
            frappe.flags.sent_mail = message
            return

        if ctx.email_account_doc.append_emails_to_sent_folder:
            ctx.email_account_doc.append_email_to_sent_folder(message)


def build_message(self, recipient_list) -> bytes:
        """Build message specific to the recipient."""
        message = self.queue_doc.message

        if not message:
            return ""

        recipient_email = recipient_list[0]

        message = message.replace(self.message_placeholder("tracker"), self.get_tracker_str(recipient_email))
        message = message.replace(
            self.message_placeholder("unsubscribe_url"), self.get_unsubscribe_str(recipient_email)
        )
        message = message.replace(self.message_placeholder("cc"), self.get_receivers_str())
        message = message.replace(
            self.message_placeholder("recipient"), self.get_recipient_str(recipient_email)
        )
        message = self.include_attachments(message)
        return message