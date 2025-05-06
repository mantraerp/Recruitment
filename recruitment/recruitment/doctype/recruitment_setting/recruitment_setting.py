# Copyright (c) 2025, Foram Shah and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import nowdate, getdate
from datetime import timedelta, datetime
from frappe.model.document import Document


class RecruitmentSetting(Document):
    pass


@frappe.whitelist()
def send_open_status_email():
    """
    Sends an email reminder for Job Applicants whose status is still 'Profile Under Review'
    after the interval defined in Recruitment Settings.
    """

    # Get the Recruitment Settings document to fetch the reminder interval
    recruitment_settings = frappe.get_single("Recruitment Setting")
    reminder_days = int(
        recruitment_settings.reminder_interval_days
    )  # Interval in days
    last_execution_date = (
        getdate(recruitment_settings.last_execution_date)
        if recruitment_settings.last_execution_date
        else None
    )
    if not last_execution_date:
        last_execution_date = getdate(nowdate())
        # Update the last execution date to today in the Recruitment Settings
        recruitment_settings.last_execution_date = nowdate()
        recruitment_settings.save()

    # Calculate the next execution date based on the reminder interval
    next_execution_date = last_execution_date + timedelta(days=reminder_days)

    # If the current date is not the next execution date, skip
    if getdate(nowdate()) != next_execution_date:
        return  # Skip execution, it's not the right time

    # Proceed with the email sending logic
    current_date = getdate(nowdate())
    cutoff_date = datetime.combine(
        current_date - timedelta(days=reminder_days), datetime.min.time()
    )
    # Fetch Job Applicants who are still 'Profile Under Review' after the cutoff date
    job_openings = frappe.get_all(
        "Job Opening",
        filters={"status": "Open"},
        fields=[
            "name",
            "department",
            "custom_hiring_manager",
            "custom_head_of_department",
        ],
    )
    if not job_openings:
        return  # No open job
    applicants = frappe.get_all(
        "Job Applicant",
        filters={
            "status": "Profile Under Review",
        },
        fields=["*"],
    )

    if not applicants:
        return  # No pending applicants; no email needed

    for job in job_openings:
        # Fetch Job Applicants linked to this Job Opening
        applicants = frappe.get_all(
            "Job Applicant",
            filters={
                "status": "Profile Under Review",
                "creation": [">=", cutoff_date],
                "job_title": job.name,  # Match with the Job Opening
            },
            fields=["*"],
        )
        if not applicants:
            continue

        # Generate the HTML table for email
        applicant_table_html = """
        <table style="border-collapse: collapse; width: 100%; margin-top: 20px;">
            <thead>
                <tr>
                    <th style="text-align: left; background-color: #E6F2A2;">Position</th>
                    <th style="text-align: left; background-color: #E6F2A2;">Name</th>
                    <th style="text-align: left; background-color: #E6F2A2;">Contact</th>
                    <th style="text-align: left; background-color: #E6F2A2;">Email</th>
                    <th style="text-align: left; background-color: #E6F2A2;">Education</th>
                    <th style="text-align: left; background-color: #E6F2A2;">Currnent Org</th>
                    <th style="text-align: left; background-color: #E6F2A2;">Experience</th>
                    <th style="text-align: left; background-color: #E6F2A2;">CTC</th>
                    <th style="text-align: left; background-color: #E6F2A2;">ECTC</th>
                    <th style="text-align: left; background-color: #E6F2A2;">Notice Period</th>
                    <th style="text-align: left; background-color: #E6F2A2;">Current Location</th>
                    <th style="text-align: left; background-color: #E6F2A2;">Remark</th>
                    
                </tr>
            </thead>
            <tbody>
        """

        for applicant in applicants:
            applicant_table_html += f"""
            <tr>
                <td>{applicant.custom_position}</td>
                <td>{applicant.applicant_name}</td>
                <td>{applicant.phone_number}</td>
                <td>{applicant.email_id}</td>
                <td>{applicant.custom_education}</td>
                <td>{applicant.custom_current_company}</td>
                <td>{applicant.custom_total_experiencein_years}</td>
                <td>{applicant.custom_current_ctc}</td> 
                <td>{applicant.custom_expected_ctc}</td>
                <td>{applicant.custom_notice_period}</td>
                <td>{applicant.custom_current_location}</td>
                <td>{applicant.Remark}</td>

            </tr>
            """

        applicant_table_html += "</tbody></table>"
        recipients = []

        # Add HOD Manager from Job Opening
        if job.custom_head_of_department:
            recipients.append(job.custom_head_of_department)

        # Add Hiring Manager from Job Opening
        if job.custom_hiring_manager:
            recipients.append(job.custom_hiring_manager)

        # Fetch all HR Managers' emails
        for hr_email in recipients:
            hr_manager_name = frappe.get_value("User", hr_email, "full_name")

            # Prepare email content
            subject = "Reminder for Shortlisting Process"
            message = f"""
            <html>
                <head>
                    <style>
                       
                        th, td {{
                            padding: 8px;
                            text-align: left;
                        }}
                        th {{
                            background-color: #E6F2A2;
                        }}
                    </style>
                </head>
                <body>
                    <p>Dear {hr_manager_name},</p>
                    <p>Greetings of the day..!!</p>
                    <p>Please find below resources:</p>
                    {applicant_table_html}
                </body>
            </html>
            """

            # Send an individual email to each HR manager
            frappe.sendmail(
                recipients=[hr_email],  # Send to one person at a time
                subject=subject,
                message=message,
                now=True,
            )
