import frappe
from frappe.utils import cint, flt, fmt_money
from frappe.utils.pdf import get_pdf
from frappe.model.document import Document
from frappe.email.queue import flush
from frappe import _
import base64
import ast
from frappe.www.printview import get_print_style
from datetime import datetime
from frappe.utils import cint, cstr, get_datetime, get_link_to_form, getdate, nowtime


@frappe.whitelist()
def make_interview_evaluation_form(source_name):
    # Get the Interview document
    interview_doc = frappe.get_doc("Interview", source_name)

    def get_day_with_suffix(day):
        if 10 <= day <= 20:  # Special case for 11th, 12th, 13th, etc.
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{day}<sup>{suffix}</sup>"

    schedule_date_format = interview_doc.scheduled_on
    final_schedule_date = schedule_date_format.strftime(
        f"{get_day_with_suffix(schedule_date_format.day)} %B %Y"
    )

    # Prepare the context for rendering the template
    context = {
        "doc": interview_doc,  # Interview document
        "css": get_print_style(),  # Include CSS for print styling
        "schedule_date": final_schedule_date,
    }
    # Render the template using the context
    html = frappe.render_template(
        "recruitment/public/js/templates/interview.html", context
    )

    # Generate the PDF from the rendered HTML
    pdf_data = get_pdf(html)

    # Encode the PDF in Base64 for return
    pdf_base64 = base64.b64encode(pdf_data).decode("utf-8")

    return pdf_base64


@frappe.whitelist()
def get_expected_skill_set(interview_round):
    # Get skills from the "Expected Skill Set" doctype
    expected_skills = frappe.get_all(
        "Expected Skill Set",
        filters={"parent": interview_round},
        fields=["skill"],
        order_by="idx",
    )

    # Get skills from the "Non Criteria" doctype
    non_criteria_skills = frappe.get_all(
        "Non Rated Criteria",
        filters={"parent": interview_round},
        fields=["criteria"],
        order_by="idx",
    )

    # Return both results separately in a dictionary
    return {
        "expected_skills": expected_skills,
        "non_criteria_skills": non_criteria_skills,
    }


@frappe.whitelist()
def create_interview_feedback(data, interview_name, interviewer, job_applicant):
    import json

    if isinstance(data, str):
        data = frappe._dict(json.loads(data))

    if frappe.session.user != interviewer:
        frappe.throw(_("Only Interviewer Are allowed to submit Interview Feedback"))

    interview_feedback = frappe.new_doc("Interview Feedback")
    interview_feedback.interview = interview_name
    interview_feedback.interviewer = interviewer
    interview_feedback.job_applicant = job_applicant

    for d in data.skill_set:
        d = frappe._dict(d)
        interview_feedback.append(
            "skill_assessment",
            {"skill": d.skill, "rating": d.rating, "custom_comment": d.comment or ""},
        )

    for d in data.criteria:
        d = frappe._dict(d)
        interview_feedback.append(
            "custom_non_rated_criteria",
            {
                "criteria": d.criteria,
                "description": d.description,
                "comment": d.comment or "",
            },
        )

    interview_feedback.feedback = data.feedback
    interview_feedback.result = data.result
    interview_feedback.custom_final_comment = data.final_feedback

    interview_feedback.save()
    interview_feedback.submit()

    frappe.msgprint(
        _("Interview Feedback {0} submitted successfully").format(
            get_link_to_form("Interview Feedback", interview_feedback.name)
        )
    )


def send_interview_feedback_notification(doc, method):
    # Fetch the related Interview
    interview = frappe.get_doc("Interview", doc.interview)

    # Get the Interview owner's email
    subject = f"Interview Feedback Submitted - [Interview ID: {interview.name}],{doc.interview_round}"

    message = f"""
    <p>Dear {frappe.db.get_value("User", interview.owner, "full_name")},</p>

    <p>The feedback for the interview of 
    <strong>{frappe.db.get_value("Job Applicant", doc.job_applicant, "applicant_name")}</strong> 
    (Interview ID: <strong>{interview.name}</strong>, Round: <strong>{doc.interview_round}</strong>) 
    has been submitted by 
    <strong>{frappe.db.get_value("User", doc.owner, "full_name")}</strong>.</p>

    <p>Regards,<br>HR Team</p>
        """
    # Send email
    frappe.sendmail(
        recipients=[interview.owner], subject=subject, message=message, now=True
    )


@frappe.whitelist()
def send_interview_cancellation_notification(docname):
    # Fetch the Interview document
    interview = frappe.get_doc("Interview", docname)
    interview.custom_is_cancel_document = 1
    interview.save()

    # Fetch Job Applicant details
    applicant = frappe.get_value(
        "Job Applicant",
        interview.job_applicant,
        ["applicant_name", "email_id"],
        as_dict=True,
    )
    applicant_name = applicant.get("applicant_name")
    applicant_email = applicant.get("email_id")

    # Fetch all Interviewer emails directly from the Interview Details child table
    interviewer_emails = frappe.get_all(
        "Interview Detail",
        filters={"parent": docname},  # Get records where parent is the Interview ID
        pluck="interviewer",  # Directly get email IDs
    )

    # Get the user who cancelled the interview
    cancelled_by = frappe.db.get_value("User", frappe.session.user, "full_name")

    # Email subject
    subject = f"Interview Cancelled - [Interview ID: {interview.name}]"

    # Email message
    message = f"""
    <p>Dear All,</p>

    <p>The interview scheduled for <strong>{applicant_name}</strong> (Interview ID: <strong>{interview.name}</strong>, Round: <strong>{interview.interview_round}</strong>) has been <strong>cancelled</strong>.</p>

    <p>This cancellation was initiated by <strong>{cancelled_by}</strong>.</p>

    <p>If you have any questions or need further details, please contact HR.</p>

    <p>Regards,<br>HR Team</p>
    """

    # Combine applicant email and interviewer emails
    recipients = [applicant_email] + interviewer_emails

    # Send email
    frappe.sendmail(
        recipients=recipients,  # Send to applicant and all interviewers
        subject=subject,
        message=message,
        now=True,
    )
    interview.submit()
    interview.cancel()
