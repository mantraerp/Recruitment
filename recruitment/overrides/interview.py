import frappe
from frappe import _
from hrms.hr.doctype.interview.interview import Interview
from frappe.utils.user import get_users_with_role
from frappe.utils.pdf import get_pdf
from frappe.utils.file_manager import save_file
from frappe.www.printview import get_print_style
from frappe.utils import get_datetime, now_datetime, add_days


class CustomInterview(Interview):
    def validate(self):
        super().validate()
        if self.to_time and self.from_time and self.to_time <= self.from_time:
            frappe.throw(_("The 'To Time' must be greater than the 'From Time'."))

        if self.interview_details:
            for detail in self.interview_details:

                if self.job_applicant == detail.interviewer:
                    frappe.throw(
                        _(
                            "Applicant email {0} cannot be the same as Interviewer's email {1}."
                        ).format(
                            frappe.bold(self.job_applicant),
                            frappe.bold(detail.interviewer),
                        ),
                        title=_("Validation Error"),
                    )

    # def on_update_after_submit(self):
    # # Call the shared method to handle email notification
    #     self.handle_interview_notification()

    def on_submit(self):
        if not self.custom_is_cancel_document:
            # Ensure the status is allowed before submitting
            if self.status not in ["Selected", "Rejected", "On Hold"]:
                frappe.throw(
                    _(
                        "Only Interviews with Cleared, Rejected, or On Hold status can be submitted."
                    ),
                    title=_("Not Allowed"),
                )

            # Ensure at least one interviewer is added
            if not self.interview_details:
                frappe.throw(
                    _(
                        "Please add at least one interviewer in the Interview Details table."
                    )
                )

            # Ensure feedback is received from all interviewers

            for detail in self.interview_details:
                if not frappe.db.exists(
                    "Interview Feedback",
                    {
                        "interviewer": detail.interviewer,
                        "interview": self.name,
                        "interview_round": self.interview_round,
                        "job_applicant": self.job_applicant,
                    },
                ):
                    interviewer_name = frappe.db.get_value(
                        "User", detail.interviewer, "full_name"
                    )
                    frappe.throw(
                        _(
                            "Interview Feedback is remaining from Interviewer {0}"
                        ).format(interviewer_name)
                    )
            self.handle_interview_notification()
            self.generate_and_attach_pdf()

    def generate_and_attach_pdf(self):
        """
        Generates an interview evaluation PDF and attaches it to the Job Applicant.
        """

        def get_day_with_suffix(day):
            if 10 <= day <= 20:  # Special case for 11th, 12th, 13th, etc.
                suffix = "th"
            else:
                suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            return f"{day}<sup>{suffix}</sup>"

        # Get interview date and format it
        schedule_date_format = get_datetime(self.scheduled_on)
        final_schedule_date = schedule_date_format.strftime(
            f"{get_day_with_suffix(schedule_date_format.day)} %B %Y"
        )
        company_logo_map = {
            "Mantra Softech": '<img src="/assets/recruitment/images/mantra_header.png"  width="100%" alt="Mantra Technologies Header"/>',
            "Mefron Technologies": '<img src="/assets/recruitment/images/mefron_header.png"  width="100%" alt="Mefron Technologies Header"/>',
            "Mewurk Technologies": "",
            "Mivanta India Pvt Ltd": '<img src="/assets/recruitment/images/mivanta_header.png"  width="100%" alt="Mivanta Technologies Header"/>',
            "Mupizo Payments": "",
            "Mocula": '<img src="/assets/recruitment/images/mocula_header.png" width="100%" alt="Mocula Technologies Header"/>',
            "Mantra Smart Identity": '<img src="/assets/recruitment/images/mantra_identity_header.png" width="100%" alt="Mantra_Identity Technologies Header"/>',
            "Mitras Global": '<img src="/assets/recruitment/images/mitras_header.png" width="100%" alt="Mitras Technologies Header"/>',
        }
        logo_url = company_logo_map.get(
            frappe.db.get_value(
                "Job Opening", self.job_opening, "custom_hiring_company"
            )
        )

        # Prepare the context for rendering the template
        context = {
            "doc": self,  # Interview document
            "css": get_print_style(),  # Include CSS for print styling
            "schedule_date": final_schedule_date,
            "header": logo_url,
        }

        # Render the HTML template
        html = frappe.render_template(
            "recruitment/public/js/templates/interview.html", context
        )

        # Generate the PDF from the rendered HTML
        pdf_data = get_pdf(html)

        # Define the file name based on the interview round
        round_label = self.interview_round.replace(
            " ", "_"
        )  # Replace spaces with underscores
        file_name = f"Interview_Evaluation_{round_label}.pdf"

        # Save the PDF file in the system
        saved_file = save_file(
            file_name, pdf_data, "Job Applicant", self.job_applicant, is_private=0
        )

        # Attach the PDF file to the Job Applicant doctype
        job_applicant_doc = frappe.get_doc("Job Applicant", self.job_applicant)
        if self.interview_round == "Round 1":
            job_applicant_doc.custom_r1_feedback = saved_file.file_url
            job_applicant_doc.status = (
                "R1 Selected" if self.status == "Selected" else "R1 Rejected"
            )
        elif self.interview_round == "Round 2":
            job_applicant_doc.custom_r2_feedback = saved_file.file_url
            job_applicant_doc.status = (
                "R2 Selected" if self.status == "Selected" else "R2 Rejected"
            )
        elif self.interview_round == "Round 3":
            job_applicant_doc.custom_r3_feedback = saved_file.file_url
            job_applicant_doc.status = (
                "R3 Selected" if self.status == "Selected" else "R3 Rejected"
            )
        job_applicant_doc.save(ignore_permissions=True)

    def handle_interview_notification(self):
        """
        Handles email notifications for interview status updates.
        """
        try:
            # Check if the status requires email notifications
            if self.status in ["Rejected", "On Hold", "Selected"]:
                # Fetch the applicant's email ID
                email_id = frappe.db.get_value(
                    "Job Applicant", self.job_applicant, "email_id"
                )

                # Get the appropriate email template
                template_doc = (
                    frappe.get_doc("Email Template", "Interview Feedback Rejection")
                    if self.status == "Rejected"
                    else frappe.get_doc("Email Template", "Interview Feedback On Hold")
                    if self.status == "On Hold"
                    else frappe.get_doc("Email Template", "Interview Feedback Selected")
                )

                # Prepare the context for rendering the email template
                context = {
                    "applicant_name": frappe.db.get_value(
                        "Job Applicant", self.job_applicant, "applicant_name"
                    ),
                    "doc": self,
                    "company": frappe.db.get_value(
                        "Job Opening", self.job_opening, "company"
                    ),
                }

                # Render the subject and message
                subject = frappe.render_template(template_doc.subject, context)
                message = frappe.render_template(template_doc.response, context)

                # Send the email
                frappe.sendmail(
                    recipients=[email_id,self.owner],
                    subject=subject,
                    message=message,
                    reference_doctype=self.doctype,
                    reference_name=self.name,
                    cc=get_users_with_role("Team Lead - Talent Acquisition"),
                    expose_recipients="header",
                    now=True,
                )

        except Exception as e:
            # Log the error and show a user-friendly message
            frappe.log_error(
                f"Error handling interview notification: {str(e)}",
                "Interview Notification Error",
            )
            frappe.throw(
                _(
                    "Unable to process the interview notification. Please check the logs."
                )
            )

    def show_job_applicant_update_dialog(self):
        job_applicant_status = self.get_job_applicant_status()
        if not job_applicant_status:
            return

        job_application_name = frappe.db.get_value(
            "Job Applicant", self.job_applicant, "applicant_name"
        )

        frappe.msgprint(
            _(
                "Do you want to update the Job Applicant {0} as {1} based on this interview result?"
            ).format(
                frappe.bold(job_application_name), frappe.bold(job_applicant_status)
            ),
            title=_("Update Job Applicant"),
            primary_action={
                "label": _("Mark as {0}").format(job_applicant_status),
                "server_action": "hrms.hr.doctype.interview.interview.update_job_applicant_status",
                "args": {
                    "job_applicant": self.job_applicant,
                    "status": job_applicant_status,
                },
            },
        )


def send_feedback_reminder():
    """Send interview feedback reminders every 24 hours if feedback is not submitted"""

    # Get all interviews with status 'Pending'
    interviews = frappe.get_all(
        "Interview",
        filters={"status": "Pending"},
        fields=[
            "name",
            "job_applicant",
            "interview_round",
            "creation",
            "custom_last_reminder_sent",
        ],
    )

    now = now_datetime()

    for interview in interviews:
        interview_details = frappe.get_all(
            "Interview Detail",
            filters={"parent": interview.name},
            fields=["name", "interviewer"],
        )

        for detail in interview_details:
            feedback_exists = frappe.db.exists(
                "Interview Feedback",
                {
                    "interview": interview.name,
                    "interviewer": detail.interviewer,
                    "job_applicant": interview.job_applicant,
                    "interview_round": interview.interview_round,
                },
            )

            if not feedback_exists:
                custom_last_reminder_sent = interview.custom_last_reminder_sent

                # Send reminder if never sent or if 24 hours have passed since the last reminder
                if not custom_last_reminder_sent or (
                    get_datetime(custom_last_reminder_sent) <= add_days(now, -1)
                ):
                    send_feedback_email(interview.name, detail.interviewer)

                    # Update the custom_last_reminder_sent timestamp in Interview doctype
                    frappe.db.set_value(
                        "Interview", interview.name, "custom_last_reminder_sent", now
                    )


def send_feedback_email(interview_name, interviewer):
    """Helper function to send email reminders for interview feedback"""
    interviewer_name = frappe.db.get_value("User", interviewer, "full_name")
    subject = "Reminder: Submit Interview Feedback"
    message = f"""
            <p>Dear {interviewer_name},</p>
            <p>This is a reminder to submit your feedback for the interview: <b>{interview_name}</b>.</p>
            <p>Please ensure you provide your feedback as soon as possible.</p>
            <p>Thank you.</p>
        """

    frappe.sendmail(recipients=interviewer, subject=subject, message=message)
