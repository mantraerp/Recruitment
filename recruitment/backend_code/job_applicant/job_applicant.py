import frappe
from frappe.utils import now_datetime, get_last_day
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils.user import get_users_with_role
import re
from bs4 import BeautifulSoup
from frappe.utils import now_datetime
from datetime import timedelta
from frappe.utils import validate_email_address


@frappe.whitelist()
def create_job_offer(source_name, target_doc=None):
    def map_item(source, target, source_parent):
        job_requisition = frappe.db.get_value(
            "Job Opening",
            frappe.db.get_value("Job Applicant", source_name, "job_title"),
            "job_requisition",
        )
        target.custom_offer_approver = frappe.db.get_value(
            "Job Requisition", job_requisition, "custom_requisition_approver"
        )

    doc = get_mapped_doc(
        "Job Applicant",
        source_name,
        {
            "Job Applicant": {
                "doctype": "Job Offer",
                "field_map": {},
                "postprocess": map_item,
            }
        },
    )
    return doc


def send_scheduled_emails():
    """
    Sends pending workflow emails that were scheduled.
    """
    try:
        now = now_datetime()
        # Fetch all Job Applicants where email is pending and scheduled time has passed
        pending_emails = frappe.get_all(
            "Job Applicant",
            filters={
                "custom_email_status": "Pending",
                "custom_email_scheduled_time": ["<=", now],
            },
            fields=["name", "email_id", "status"],
        )
        for job_applicant in pending_emails:
            doc = frappe.get_doc("Job Applicant", job_applicant.name)
            template_name = None
            # Define the template name based on the action
            if doc.status == "Shortlisted":
                template_name = "Job Applicant Shortlisted"
            elif doc.status == "Not Shortlisted":
                template_name = "Job Applicant is Rejected"
            context = {
                "company": frappe.db.get_value("Job Opening", doc.job_title, "company"),
                "doc": doc,
            }
            if template_name:
                template_doc = frappe.get_doc("Email Template", template_name)
            else:
                continue
            subject = frappe.render_template(template_doc.subject, context)
            message = frappe.render_template(template_doc.response, context)
            frappe.sendmail(
                recipients=[doc.email_id,doc.owner],
                subject=subject,
                message=message,
                reference_doctype="Job Applicant",
                reference_name=doc.name,
                now=True,
            )
            # Mark email as sent
            doc.db_set("custom_email_status", "Sent")
            doc.save()
        return f"Processed {len(pending_emails)} pending emails."
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Scheduled Email Processing Error")


@frappe.whitelist()
def send_document_request(applicant, applicant_email, name, hiring_company, position):
    """
    Sends pending workflow emails that were scheduled.
    """
    try:
        context = {
            "applicant_name": applicant,
            "company": hiring_company,
            "position": position,
        }
        template_doc = frappe.get_doc(
            "Email Template", "Document Submission Required for Further Process"
        )
        subject = frappe.render_template(template_doc.subject, context)
        message = frappe.render_template(template_doc.response, context)
       
        
        frappe.sendmail(
            recipients=[applicant_email,frappe.db.get_value("Job Applicant", name, "owner")],
            subject=subject,
            message=message,
            reference_doctype="Job Applicant",
            reference_name=name,
            cc=get_users_with_role("Team Lead - Talent Acquisition"),
            now=True,
        )
        frappe.db.set_value(
            "Job Applicant", name, "custom_send_document_request_email", 1
        )
        frappe.db.commit()  # Ensure changes are committed to the database
        return True
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Scheduled Email Processing Error")


def clean_quill_html(html_content):
    """Cleans up Quill.js HTML to properly format bullet points in email"""

    # Parse HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove all <span class="ql-ui"> elements
    for span in soup.find_all("span", class_="ql-ui"):
        span.decompose()

    # Convert <ol> or <ul> with `data-list="bullet"` into proper <ul>
    for li in soup.find_all("li"):
        if "data-list" in li.attrs:
            del li["data-list"]  # Remove invalid attribute

    # Wrap orphan <li> elements inside a <ul>
    for li in soup.find_all("li"):
        if not li.find_parent(["ul", "ol"]):  # Check if li is not inside a list
            ul = soup.new_tag(
                "ul", style="list-style-type: disc !important; padding-left: 20px;"
            )
            li.wrap(ul)

    return str(soup)


@frappe.whitelist()
def send_job_description_to_applicant(doc, method=None):
    """
    Handles workflow actions for Job Requisition, including sending emails using templates.

    Args:
        doc_name (str): Name of the Job Requisition document.
        action (str): Action performed in the workflow ("approve" or "reject").
        reason (str, optional): Reason for rejection (if applicable).
    """
    try:
        company_website_links = {
            "Mantra Softech (India) Private Limited": "https://www.mantratec.com/",
            "Mefron Technologies (India) Private Limited": "https://www.mefron.com/",
            "Mewurk Technologies Private Limited": "https://www.mewurk.com/",
            "Mivanta India Private Limited": "https://www.mivanta.com/",
            "Mupizo Payments Private Limited": "https://mupizo.com/",
            "Mocula Optics Technologies Private Limited": "https://www.indiafilings.com/search/mocula-optics-technologies-private-limited-cin-U26700GJ2024PTC148706",
            "Mantra Smart Identity Private Limited": "https://mantraidentity.com/",
            "Mitras Global Private Limited": "https://www.mitraspro.com/",
        }
        context = {
            "doc": doc,
            "owner_mobile_no": frappe.db.get_value("User", doc.owner, "mobile_no"),
            "website_link": company_website_links.get(f"{doc.custom_hiring_company}"),
        }

        message = f"""
                <body>
                <style>
                 ol li{{
                list-style-type: disc !important;
            }}  </style>
                <p>Dear { doc.applicant_name },</p>
                <p>Thank you for your interest in the <strong>{doc.custom_position}</strong> role at <strong>{doc.custom_hiring_company}</strong>! We have received your application and are currently reviewing your profile.</p>
                <p>Below are the details of the position you have applied for:</p>
                <ul>
                    <li><strong>Job Title:</strong> {doc.custom_position}</li>
                    <li><strong>Job Location:</strong> {doc.custom_location}</li>
                </ul>
                <p><strong>Job Description:</strong></p>
                <p style="margin-top:0px !important;">{clean_quill_html(doc.description)}</p>
                
                <p>We will be carefully evaluating your qualifications and experience. If your profile is shortlisted, we will reach out to you with the next steps.</p>
                <p>We appreciate your interest in joining <strong>{doc.custom_hiring_company} </strong> and the time you've taken to apply for this position.</p>
                <p>If you have any questions or need further information, please don't hesitate to contact us at <a href='mailto:{doc.owner}'>{doc.owner}</a> or {context['owner_mobile_no']}.</p>
                <p>We wish you the best of luck in your job search and look forward to connecting with you soon.</p>
                <p>For more details about our company, please visit our website: <a href='{ context['website_link'] }' target='_blank'>{ context['website_link'] }</a>.</p>
                <p>Best Regards,</p>
                <p><strong>{doc.custom_hiring_company} Team</strong></p>
            </body>"""
        # Send the email
        frappe.sendmail(
            cc=get_users_with_role("Team Lead - Talent Acquisition"),
            expose_recipients="header",
            recipients=[doc.email_id,doc.owner],
            subject=f"Your Application for {doc.custom_position} at {doc.custom_hiring_company}",
            message=message,
            reference_doctype="Job Applicant",
            reference_name=doc.name,
            now=True,
        )
    except Exception as e:
        # Log the error and show a user-friendly message
        frappe.log_error(
            f"Error handling workflow action: {str(e)}", "Workflow Action Error"
        )
        frappe.throw("Unable to process the workflow action. Please check the logs.")


def validate_duplicates_for_job_opening(doc, method=None):
    if doc.is_new():
        doc.custom_created_by = frappe.session.user
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


def validate_duplicates_for_job_applicant(doc, method=None):
    validate_email_address(doc.email_id, throw=True)
    if doc.is_new():
            duplicate = frappe.db.exists(
                "Job Applicant",
                {
                    "designation": doc.designation,
                    "custom_department": doc.custom_department,
                    "email_id":doc.email_id,
                    "status":['in',['Draft','Send to Team Leader','Profile Under Review','Shortlisted','R1 Selected','R2 Selected','R3 Selected','Offer Released','Offer Accepted','Joined']],
                    "custom_hiring_company":doc.custom_hiring_company,
                    'job_title':doc.job_title
                },
            )
            if duplicate:
                frappe.throw(
                    _("A Job Applicant for {0} with Hiring Company {1} in Department {2} already exists").format(
                        frappe.bold(doc.designation),
                        frappe.bold(doc.custom_hiring_company),
                        frappe.bold(doc.custom_department)
                    ),
                    title=_("Duplicate Job Applicant"),
                )
    round_status_map = {
        "R1 Selected": ["Round 1"],
        "R1 Rejected": ["Round 1"],
        "R2 Selected": ["Round 1", "Round 2"],
        "R2 Rejected": ["Round 1", "Round 2"],
        "R3 Selected": ["Round 1", "Round 2", "Round 3"],
        "R3 Rejected": ["Round 1", "Round 2", "Round 3"],
    }
    round_status_map_1 = {
        "R1 Selected": "Round 1",
        "R1 Rejected": "Round 1",
        "R2 Selected": "Round 2",
        "R2 Rejected": "Round 2",
        "R3 Selected": "Round 3",
        "R3 Rejected": "Round 3",
        "R4 Selected": "Round 4",
        "R4 Rejected": "Round 4",
    }
    existing_interviews = frappe.db.get_list(
        "Interview",
        filters={"job_applicant": doc.name, "docstatus": 1},
        fields=["interview_round", "status"],
    )

    # Create a map of round statuses
    interview_round_status_map = {
        interview["interview_round"]: interview["status"]
        for interview in existing_interviews
    }

    # Ensure that no rejected round is later marked as selected
    new_round_status = round_status_map_1.get(doc.status)
    if new_round_status in interview_round_status_map:
        previous_status = interview_round_status_map[new_round_status]
        if ("Rejected" in previous_status and "Selected" in doc.status) or (
            "Selected" in previous_status and "Rejected" in doc.status
        ):
            frappe.throw(
                _(
                    f"Cannot change status to {doc.status}. '{new_round_status}' was already marked as '{previous_status}'."
                )
            )
    required_rounds = round_status_map.get(doc.status, [])
    if required_rounds:
        existing_rounds = {
            interview
            for interview in frappe.db.get_list(
                "Interview",
                filters={
                    "job_applicant": doc.name,
                    "interview_round": ["in", required_rounds],
                    "docstatus": 1,
                },
                pluck="interview_round",
            )
        }
        missing_rounds = set(required_rounds) - existing_rounds
        if missing_rounds:
            frappe.throw(
                _(
                    f"Cannot update status to {doc.status}. Missing Interview rounds: {', '.join(missing_rounds)}."
                )
            )
    job_applicant_status_map = {
        "Offer Released": "Offer Released",
        "Offer Accepted": "Offer Accepted",
        "Offer Declined": "Offer Declined",
    }
    # Check if the selected Job Applicant status requires a Job Offer validation
    required_job_offer_status = job_applicant_status_map.get(doc.status)
    if required_job_offer_status:
        # Check if there is an existing Job Offer with the required status
        job_offer_exists = frappe.db.exists(
            "Job Offer",
            {
                "job_applicant": doc.name,
                "status": ["in", [required_job_offer_status]],
                "docstatus": 1,
            },
        )
        if not job_offer_exists:
            frappe.throw(
                _(
                    f"Cannot update status to {doc.status}. No Job Offer found with status '{required_job_offer_status}'."
                )
            )


def send_daily_report():
    # Get the current date and time
    current_datetime = now_datetime()
    # Set the start time to 24 hours ago, i.e., yesterday at 10 PM
    start_time = current_datetime - timedelta(days=1)
    # Set the end time to the current time, i.e., today at 10 PM
    end_time = current_datetime
    # Format times to match the date format in the database
    start_time_str = start_time.replace(hour=22, minute=0, second=0, microsecond=0)
    end_time_str = end_time.replace(hour=22, minute=0, second=0, microsecond=0)
    # Get recruiters (users with the role "HR User - Recruitment Executive")
    tl_hr_users = get_users_with_role("Team Lead - Talent Acquisition")
    recruitment_manager = get_users_with_role("Manager - Talent Acquisition")
    # Merge both lists and remove duplicates
    recipients = list(set(tl_hr_users + recruitment_manager))
    recruiters = get_users_with_role("Talent Acquisition Executive")
    # Initialize the table rows for the email
    table_rows = ""
    # Iterate through each recruiter to gather the required data
    for recruiter in recruiters:
        recruiter_name = frappe.db.get_value("User", recruiter, "full_name")
        recruiter_email = frappe.db.get_value("User", recruiter, "email")
        # Job Applicants Submitted
        job_applicants_count = len(
            frappe.db.get_list(
                "Job Applicant",
                filters={
                    "owner": recruiter_email,
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        # Total Interviews Conducted
        total_interviews_count = frappe.db.sql(
            """
            SELECT COUNT(*) 
            FROM `tabInterview Detail` id
            JOIN `tabInterview` i ON id.parent = i.name
            WHERE id.interviewer = %s
            AND i.creation BETWEEN %s AND %s
        """,
            (recruiter_email, start_time_str, end_time_str),
            as_dict=False,
        )[0][0]
        # Final Selections
        final_selections_count = len(
            frappe.db.get_list(
                "Interview",
                filters={
                    "owner": recruiter_email,
                    "interview_round": "Round 2",
                    "status": "Selected",
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        # Joiners
        joiners_count = len(
            frappe.db.get_list(
                "Job Applicant",
                filters={
                    "status": "Joined",
                    "owner": recruiter_email,
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        # Offers
        offers_count = len(
            frappe.db.get_list(
                "Job Offer",
                filters={
                    "owner": recruiter_email,
                    "workflow_state": "Approved",
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        # Format each recruiter's data into a table row
        table_row = f"""
        <tr>
            <td style="text-align:center;">{recruiter_name}</td>
            <td style="text-align:center;">{recruiter_email}</td>
            <td style="text-align:center;">{job_applicants_count}</td>
            <td style="text-align:center;">{total_interviews_count}</td>
            <td style="text-align:center;">{final_selections_count}</td>
            <td style="text-align:center;">{joiners_count}</td>
            <td style="text-align:center;">{offers_count}</td>
        </tr>
        """
        # Append the row to the table
        table_rows += table_row
    # HTML content for the email
    email_html = f"""
    <p>Dear Team Leads and Recruitment Head,</p>
    <p>Here is the daily recruitment summary for the period from {start_time_str.strftime('%Y-%m-%d %H:%M:%S')} to {end_time_str.strftime('%Y-%m-%d %H:%M:%S')}:</p>
    <table border="1" cellpadding="5" cellspacing="0">
        <thead>
            <tr>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Recruiters Name</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Recruiter's Email ID</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Job Applicants Submitted</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Total Interviews Conducted</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Final Selections</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Joiners</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Offers</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
    <p>Best regards,</p>
    <p>The Recruitment Team</p>
    """
    # Send the email
    frappe.sendmail(
        recipients=recipients,
        subject=f"Daily Recruitment Report - {end_time_str.strftime('%Y-%m-%d')}",
        message=email_html,
        now=True,
    )


def check_and_send_monthly_report():
    """Check if today is the last day of the month, then send the report."""

    current_date = now_datetime().date()
    last_day_of_month = get_last_day(current_date)

    # Only proceed if today is the last day of the month
    if current_date == last_day_of_month:
        send_monthly_report()


def send_monthly_report():
    # Get the current date and time
    current_datetime = now_datetime()
    # Get the start and end of the month
    start_time = current_datetime.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    end_time = current_datetime.replace(hour=22, minute=0, second=0, microsecond=0)
    # Format times for queries
    start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
    # Get recruiters (users with the role "HR User - Recruitment Executive")
    tl_hr_users = get_users_with_role("Team Lead - Talent Acquisition")
    recruitment_manager = get_users_with_role("Manager - Talent Acquisition")
    # Merge both lists and remove duplicates
    recipients = list(set(tl_hr_users + recruitment_manager))
    recruiters = get_users_with_role("Talent Acquisition Executive")
    # Initialize recruiter performance list
    recruiter_data = []
    # Iterate through each recruiter to gather performance data
    for recruiter in recruiters:
        recruiter_name = frappe.db.get_value("User", recruiter, "full_name")
        recruiter_email = frappe.db.get_value("User", recruiter, "email")
        # Job Applicants Submitted
        job_applicants_count = len(
            frappe.db.get_list(
                "Job Applicant",
                filters={
                    "owner": recruiter_email,
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        # Status breakdown
        profile_under_review = len(
            frappe.db.get_list(
                "Job Applicant",
                filters={
                    "owner": recruiter_email,
                    "status": "Profile Under Review",
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        candidate_backed_out = len(
            frappe.db.get_list(
                "Job Applicant",
                filters={
                    "owner": recruiter_email,
                    "status": "Candidate Backed Out",
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        offer_declined = len(
            frappe.db.get_list(
                "Job Applicant",
                filters={
                    "owner": recruiter_email,
                    "status": "Offer Declined",
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        shortlisted = len(
            frappe.db.get_list(
                "Job Applicant",
                filters={
                    "owner": recruiter_email,
                    "status": "Shortlisted",
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        # Calculate Shortlisting Ratio
        shortlisting_ratio = (
            (shortlisted / job_applicants_count * 100) if job_applicants_count else 0
        )
        # Total Interviews Conducted
        total_interviews_count = frappe.db.sql(
            """
            SELECT COUNT(*) 
            FROM `tabInterview Detail` id
            JOIN `tabInterview` i ON id.parent = i.name
            WHERE id.interviewer = %s
            AND i.creation BETWEEN %s AND %s
        """,
            (recruiter_email, start_time_str, end_time_str),
            as_dict=False,
        )[0][0]
        # Final Selections
        final_selections_count = len(
            frappe.db.get_list(
                "Interview",
                filters={
                    "owner": recruiter_email,
                    "interview_round": "Round 2",
                    "status": "Selected",
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        # Joiners
        joiners_count = len(
            frappe.db.get_list(
                "Job Applicant",
                filters={
                    "status": "Joined",
                    "owner": recruiter_email,
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        # Offers
        offers_count = len(
            frappe.db.get_list(
                "Job Offer",
                filters={
                    "owner": recruiter_email,
                    "workflow_state": "Approved",
                    "creation": ["between", start_time_str, end_time_str],
                },
            )
        )
        # Store data for sorting
        recruiter_data.append(
            {
                "name": recruiter_name,
                "email": recruiter_email,
                "job_applicants_count": job_applicants_count,
                "total_interviews_count": total_interviews_count,
                "shortlisted": shortlisted,
                "shortlisting_ratio": shortlisting_ratio,
                "profile_under_review": profile_under_review,
                "final_selections_count": final_selections_count,
                "joiners_count": joiners_count,
                "offers_count": offers_count,
                "candidate_backed_out": candidate_backed_out,
                "offer_declined": offer_declined,
            }
        )
    # Sort recruiters based on the ranking criteria (ascending order)
    recruiter_data.sort(
        key=lambda x: (
            -x["joiners_count"],  # Highest joiners first
            -x["offers_count"],  # Then offers
            -x["job_applicants_count"],  # Then submissions
            -x["shortlisting_ratio"],  # Then shortlisting ratio
            -x["total_interviews_count"],  # Finally, interviews scheduled
        )
    )
    # Construct table rows
    table_rows = "".join(
        f"""
        <tr>
            <td style="text-align:center;">{data["name"]}</td>
            <td style="text-align:center;">{data["email"]}</td>
            <td style="text-align:center;">{data["job_applicants_count"]}</td>
            <td style="text-align:center;">{data["total_interviews_count"]}</td>
            <td style="text-align:center;">{data["shortlisted"]}</td>
            <td style="text-align:center;">{data["shortlisting_ratio"]:.2f}</td>
            <td style="text-align:center;">{data["profile_under_review"]}</td>
            <td style="text-align:center;">{data["final_selections_count"]}</td>
            <td style="text-align:center;">{data["joiners_count"]}</td>
            <td style="text-align:center;">{data["offers_count"]}</td>
            <td style="text-align:center;">{data["candidate_backed_out"]}</td>
            <td style="text-align:center;">{data["offer_declined"]}</td>
        </tr>
    """
        for data in recruiter_data
    )
    # Email HTML content
    email_html = f"""
    <p>Dear Team Leads and Recruitment Head,</p>
    <p>Here is the monthly recruitment summary for {current_datetime.strftime('%B %Y')}:</p>
    <table border="1" cellpadding="5" cellspacing="0">
        <thead>
            <tr>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Recruiters Name</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Recruiter's Email ID</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Job Applicants Submitted</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Total Interviews Conducted</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Shortlisted Candidates</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Shortlisting Ratio</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Profile Under Review</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Final Selections</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Joiners</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Offers</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Candidate Backed Out</th>
                <th style="background-color:rgb(52, 152, 219);text-align:center;">Offer Declined</th>
            </tr>
        </thead>
        <tbody>{table_rows}</tbody>
    </table>
    <p>Best regards,</p>
    <p>The Recruitment Team</p>
    """
    # Send the email
    frappe.sendmail(
        recipients=recipients,
        subject=f"Monthly Recruitment Report - {current_datetime.strftime('%B %Y')}",
        message=email_html,
        now=True,
    )
