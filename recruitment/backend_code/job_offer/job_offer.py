import frappe
import os
from frappe.utils import flt
import frappe.utils
from frappe.utils.pdf import get_pdf
from frappe import _
import base64
from frappe.utils.user import get_users_with_role
from hrms.payroll.doctype.salary_slip.salary_slip import _safe_eval
from frappe.utils import now_datetime, flt
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP
from frappe.utils.user import get_users_with_role
from mantra_dev.backend_code.globle import create_notification_log


def _safe_eval(expression, context):
    try:
        return eval(expression, {"__builtins__": {}}, context)
    except Exception as e:
        frappe.log_error(
            f"Error in formula evaluation: {expression} - {str(e)}",
            "Salary Structure Evaluation",
        )
        return 0


def evaluate_formula_split(formula, context):
    """
    Evaluate a formula by splitting it into smaller chunks.
    """
    try:
        formula_chunks = formula.split("AND")  # Example: Split by logical AND
        result = sum(_safe_eval(chunk.strip(), context) for chunk in formula_chunks)
        return result
    except Exception as e:
        frappe.log_error(
            f"Error evaluating formula: {formula} - {str(e)}",
            "Salary Structure Evaluation",
        )
        return 0


def fetch_component_formula(abbr):
    """Fetch the formula for a given salary component abbreviation from the database."""
    formula = frappe.db.get_value(
        "Salary Component", {"salary_component_abbr": abbr}, "formula"
    )
    if formula:
        return formula  # Return formula if found
    return frappe.db.get_value(
        "Salary Component", {"salary_component_abbr": abbr}, "amount"
    )  # Otherwise, return amount


def extract_variables(formula):
    """Extracts variables from a formula string."""
    return [
        var.strip()
        for var in formula.replace("(", " ")
        .replace(")", " ")
        .replace("+", " ")
        .replace("-", " ")
        .split()
        if var.strip()
    ]


def calculate_salary_components(
    job_offer_doc,
    salary_structure,
    ctc,
    payment_days=None,
    total_working_days=1,
    custom_pf_type=None,
    custom_additional_pf=None,
    custom_stateprovince_for_pt=None,
):
    base = flt(ctc) / 12
    context = {
        "ctc": base,
        "payment_days": payment_days or 0,
        "total_working_days": total_working_days,
        "custom_pf_type": custom_pf_type,
        "custom_additional_pf": custom_additional_pf or "",
        "base": base,
        "custom_stateprovince_for_pt": custom_stateprovince_for_pt,
    }

    # First, store all direct amounts and formulas in context
    pending_formulas = {}
    for component in salary_structure.get("earnings", []) + salary_structure.get(
        "deductions", []
    ):
        abbr, amount = component.get("abbr"), component.get("amount")
        formula = component.get("formula") or fetch_component_formula(
            abbr
        )  # Fetch formula from Salary Component if not provided
        if abbr:
            if formula:
                pending_formulas[abbr] = formula  # Store formula for later evaluation
            elif amount is not None:
                context[
                    abbr
                ] = amount  # Store base value in context if no formula exists

    def evaluate_with_dependencies(abbr, salary_structure, context, is_deduction=False):
        """Recursively evaluates formula components that have dependencies."""
        if abbr in context:
            return context[abbr]

        # Check if the component exists in the earnings table (if not a deduction)
        component = (
            next(
                (
                    c
                    for c in salary_structure.get("earnings", [])
                    if c.get("abbr") == abbr
                ),
                None,
            )
            if not is_deduction
            else next(
                (
                    c
                    for c in salary_structure.get("deductions", [])
                    if c.get("abbr") == abbr
                ),
                None,
            )
        )

        formula = None
        if component:
            formula = component.get("formula") or fetch_component_formula(abbr)
        else:
            formula = fetch_component_formula(
                abbr
            )  # Fetch even if not in earnings/deductions

        if isinstance(formula, (int, float)):
            context[abbr] = formula
            return formula

        if isinstance(formula, str) and formula.strip():
            dependencies = extract_variables(formula)
            temp_context = context.copy()  # Temporary context for calculation
            for var in dependencies:
                if var not in context:
                    if not is_deduction:  # Only treat as 0 in calculations for earnings
                        temp_context[var] = (
                            evaluate_with_dependencies(var, salary_structure, context)
                            if var
                            in [
                                c.get("abbr")
                                for c in salary_structure.get("earnings", [])
                            ]
                            else 0
                        )
                    else:
                        temp_context[var] = evaluate_with_dependencies(
                            var, salary_structure, context, is_deduction=True
                        )

            context[abbr] = evaluate_formula_split(formula, temp_context)
            return context[abbr]

        context[abbr] = 0 if not is_deduction else context.get(abbr, 0)
        return context[abbr]

    import math

    def process_components(components, salary_structure, context, is_deduction=False):
        total = 0
        result = []

        # Define components to exclude from deductions
        excluded_deductions = {
            "Income Tax",
            "Income Tax - 194C",
            "Income Tax - 194J",
            "Loan Repayment",
            "Other Deduction",
        }
        excluded_earnings = {"Gratuity"}

        for component in components:
            abbr = component.get("abbr")
            is_statical = component.get("statistical_component", 0)
            salary_component_name = component.get("salary_component")

            # Skip excluded deductions
            if is_deduction and salary_component_name in excluded_deductions:
                continue

            if not is_deduction and salary_component_name in excluded_earnings:
                continue

            if abbr:
                value = evaluate_with_dependencies(
                    abbr, salary_structure, context, is_deduction
                )
            else:
                value = 0

            # Apply ceil and keep 2 decimal places
            value = math.ceil(value * 100) / 100

            if not is_statical:
                total += value  # Accumulate values

                result.append(
                    {
                        "salary_component": salary_component_name,
                        "amount": value,  # Store ceiled value
                    }
                )

        return result, total

    earnings, total_earnings = process_components(
        salary_structure.get("earnings", []),
        salary_structure,
        context,
        is_deduction=False,
    )
    deductions, total_deductions = process_components(
        salary_structure.get("deductions", []),
        salary_structure,
        context,
        is_deduction=True,
    )
    return {
        "earnings": earnings,
        "deductions": deductions,
        "total_earnings": round(total_earnings, 0),
        "total_deductions": round(total_deductions, 0),
    }


@frappe.whitelist()
def get_gratuity_value(docname):
    # Fetch Job Offer Document
    job_offer_doc = frappe.get_doc("Job Offer", docname)

    if not job_offer_doc.custom_salary_structure:
        frappe.throw("Salary Structure is not selected")

    # Fetch Salary Structure
    salary_structure_doc = frappe.get_doc(
        "Salary Structure", job_offer_doc.custom_salary_structure
    )

    # Calculate Salary Components
    calculated_data = calculate_salary_components(
        job_offer_doc=job_offer_doc,
        salary_structure=salary_structure_doc,
        ctc=job_offer_doc.custom_fixed_ctc,
        payment_days=31,  # Adjust as needed
        total_working_days=31,  # Adjust as needed
        custom_pf_type=job_offer_doc.custom_pf_type,
        custom_additional_pf=job_offer_doc.custom_addtional_pf or 0,
        custom_stateprovince_for_pt=job_offer_doc.custom_stateprovince_for_pt,
    )

    # Fetch Basic Salary from earnings
    basic_salary = next(
        (
            earning["amount"]
            for earning in calculated_data.get("earnings", [])
            if earning["salary_component"] == "Basic"
        ),
        0,
    )

    # Calculate Gratuity
    gratuity = round((4.81 / 100) * basic_salary, 2)
    nps = round((10 / 100) * basic_salary, 2)

    return {"gratuity": gratuity, "nps": nps}


def get_day_with_suffix(day):
    if 10 <= day <= 20:  # Special case for 11th, 12th, 13th, etc.
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}<sup> {suffix}</sup>"


@frappe.whitelist()
def download_job_offer_pdf(docname, action=None):
    job_offer_doc = frappe.get_doc("Job Offer", docname)
    html_template = ""
    body_width = (
        'style="width:50%;"' if action == "Preview Job Offer" else 'style="width:auto;"'
    )
    company_assets = {
        "Mefron Technologies (India) Private Limited": "mefron",
        "Mantra Softech (India) Private Limited": "mantra",
        "Mitras Global Private Limited": "mitras",
        "Mocula Optics Technologies Private Limited": "mocula",
        "Mantra Smart Identity Private Limited": "mantra_identity",
        "Mivanta India Private Limited": "mivanta",
    }
    company_key = company_assets.get(job_offer_doc.custom_hiring_company)
    header = footer = ""
    if company_key:
        header = f'<img src="/assets/recruitment/images/{company_key}_header.png" width="100%" alt="{job_offer_doc.custom_hiring_company} Header"/>'
        footer = f'<img src="/assets/recruitment/images/{company_key}_footer.png" width="100%" alt="{job_offer_doc.custom_hiring_company} Footer"/>'
    template_data = {}

    if job_offer_doc.custom_employment_type == "Consultant":
        consultant_dates = {
            "consultant_date": job_offer_doc.custom_consultant_agreement_date,
            "consultant_from_date": job_offer_doc.custom_from_date,
            "consultant_to_date": job_offer_doc.custom_till_date,
        }
        template_data["doc"] = job_offer_doc
        template_data["company"] = job_offer_doc.custom_hiring_company
        template_data["header"] = header
        template_data["footer"] = footer
        template_data["body_width"] = body_width
        template_data.update(
            {
                key: value.strftime(f"{get_day_with_suffix(value.day)} %B %Y")
                for key, value in consultant_dates.items()
            }
        )
        month_difference = (
            relativedelta(
                job_offer_doc.custom_till_date, job_offer_doc.custom_from_date
            ).years
            * 12
            + relativedelta(
                job_offer_doc.custom_till_date, job_offer_doc.custom_from_date
            ).months
        )
        template_data[
            "month_difference"
        ] = f"{frappe.utils.money_in_words(month_difference, main_currency='').split(' ')[1]} ({month_difference}) {'month' if month_difference == 1 else 'months'}"

        template_data["doc"] = job_offer_doc
        company_name = job_offer_doc.custom_hiring_company
        template_data["company"] = company_name

        if job_offer_doc.custom_standard_sales_format:
            html_template = "recruitment/public/js/templates/consultant_agreement1.html"
        else:
            html_template = "recruitment/public/js/templates/consultant_agreement.html"

    else:
        calculated_data = None
        if job_offer_doc.workflow_state == "Approved":
            if not job_offer_doc.custom_salary_structure:
                frappe.throw("Salary Structure is not Selected")
            salary_structure_doc = frappe.get_doc(
                "Salary Structure", job_offer_doc.custom_salary_structure
            )

            calculated_data = calculate_salary_components(
                job_offer_doc=job_offer_doc,
                salary_structure=salary_structure_doc,
                ctc=job_offer_doc.custom_fixed_ctc,
                payment_days=31,
                total_working_days=31,
                custom_pf_type=job_offer_doc.custom_pf_type,
                custom_additional_pf=job_offer_doc.custom_addtional_pf or 0,
                custom_stateprovince_for_pt=job_offer_doc.custom_stateprovince_for_pt,
            )

            employer_pf_contribution = sum(
                d["amount"]
                for d in calculated_data["deductions"]
                if d["salary_component"] == "Employer's Contribution to PF"
            )
            employer_esic_contribution = sum(
                e["amount"]
                for e in calculated_data["earnings"]
                if e["salary_component"] == "Employer's Contribution to ESIC"
            )

            calculated_data.update(
                {
                    "earnings": [
                        e
                        for e in calculated_data["earnings"]
                        if e["salary_component"] != "Employer's Contribution to ESIC"
                    ],
                    "deductions": [
                        d
                        for d in calculated_data["deductions"]
                        if d["salary_component"] != "Employer's Contribution to PF"
                    ],
                    "total_earnings": round(calculated_data["total_earnings"], 0)
                    - employer_esic_contribution,
                    "total_deductions": round(calculated_data["total_deductions"], 0)
                    - employer_pf_contribution,
                    "employer_pf_contribution": employer_pf_contribution,
                    "employer_esic_contribution": employer_esic_contribution,
                }
            )

            if job_offer_doc.custom_gratuity:
                gratuity_amount = job_offer_doc.custom_gratuity_amount
                calculated_data["total_earnings"] -= gratuity_amount
                for earning in calculated_data["earnings"]:
                    if earning.get("salary_component") == "Special Allowance":
                        earning["amount"] -= gratuity_amount
                        break

            if job_offer_doc.custom_nps:
                calculated_data["total_deductions"] += job_offer_doc.custom_nps_amount

        offer_date = job_offer_doc.offer_date.strftime(
            f"{get_day_with_suffix(job_offer_doc.offer_date.day)} %B %Y"
        )
        joining_date = job_offer_doc.custom_date_of_joining.strftime(
            f"{get_day_with_suffix(job_offer_doc.custom_date_of_joining.day)} %B %Y"
        )
        company_name = job_offer_doc.custom_hiring_company

        probation_in_words = frappe.utils.money_in_words(
            job_offer_doc.custom_probation_period_in_month, main_currency=""
        ).split(" ")[1]

        template_data = {
            "doc": job_offer_doc,
            "offer_date": offer_date,
            "joining_date": joining_date,
            "company": company_name,
            "body_width": body_width,
            "calculated_data": calculated_data if calculated_data else "",
            "footer": footer,
            "header": header,
            "probation_month": probation_in_words,
        }

        if job_offer_doc.custom_employment_type == "Intern":
            pdf_content = get_pdf(
                frappe.get_print(
                    job_offer_doc.doctype, docname, "Trainee Job Offer Format"
                )
            )
            template_data["annxture"] = pdf_content
            template_data["traning_month"] = frappe.utils.money_in_words(
                job_offer_doc.custom_training_period_in_months, main_currency=""
            ).split(" ")[1]
            html_template = "recruitment/public/js/templates/trainee_offer_format.html"

        elif job_offer_doc.custom_employment_type == "Full-Time":
            html_file_mapping = {
                (False, False): "with_salary_format.html",
                (True, False): "without_department_format.html",
                (False, True): "without_salary_format.html",
            }
            html_template = f"recruitment/public/js/templates/{html_file_mapping.get((job_offer_doc.custom_without_department, job_offer_doc.custom_with_annexure))}"

    if action == "Preview Job Offer":

        template_data["is_extra_space"] = 0
        html = frappe.render_template(html_template, template_data)
        return html
    elif action == "Download Job Offer":
        template_data["is_extra_space"] = 1
        html = frappe.render_template(html_template, template_data)
        pdf_content = get_pdf(
            html,
            options={"page-size": "A4", "margin-top": "0mm", "margin-bottom": "0mm"},
        )
        if job_offer_doc.custom_employment_type in ["Full-Time", "Intern"]:
            return {
                "pdf_base64": base64.b64encode(pdf_content).decode("utf-8"),
                "filename": f"{job_offer_doc.applicant_name}_job_offer_{job_offer_doc.name}.pdf",
            }
        else:
            return {
                "pdf_base64": base64.b64encode(pdf_content).decode("utf-8"),
                "filename": f"{job_offer_doc.applicant_name}_consultant_agreement.pdf",
            }
    elif action == "Send Job Offer":
        pdf = get_pdf(
            html,
            options={"page-size": "A4", "margin-top": "0mm", "margin-bottom": "0mm"},
        )
        frappe.msgprint(_("The job offer PDF has been sent to the applicant's email."))
        send_email_with_attachment(job_offer_doc.applicant_email, pdf)


def send_email_with_attachment(email, pdf):
    """Send the job offer PDF to the applicant's email."""
    frappe.sendmail(
        recipients=email,
        subject="Job Offer",
        message="Please find your job offer attached.",
        attachments=[
            {
                "fname": "Job_Offer.pdf",
                "fcontent": pdf,
            }
        ],
        now=True,
    )


import frappe
from frappe.utils import add_days, today


@frappe.whitelist()
def send_joining_reminders():
    """
    Runs daily to check if date_of_joining - 3 days matches today.
    Sends reminder emails for such job offers.
    """
    # Get today's date
    today_date = today()
    # Fetch job offers where date_of_joining - 3 days equals today
    job_offers = frappe.get_all(
        "Job Offer",
        filters={
            "workflow_state": "Offer Accepted",  # Only approved job offers
            "custom_date_of_joining": add_days(
                today_date, 3
            ),  # Joining date is 3 days ahead
        },
        fields=["*"],
    )
    # If no job offers found, log and exit
    if not job_offers:
        frappe.log_error("No job offers found for reminders", "Job Offer Reminder")
        return
    # Process each job offer
    for job in job_offers:
        try:
            date_of_joining = job["custom_date_of_joining"]
            joining_date = date_of_joining.strftime(
                f"{get_day_with_suffix(date_of_joining.day)} %B %Y"
            )
            html = frappe.render_template(
                "recruitment/public/js/templates/annexure.html"
            )
            pdf = get_pdf(
                html,
                {
                    "margin-left": "10mm",
                    "margin-right": "10mm",
                    "margin-top": "10mm",
                    "margin-bottom": "10mm",
                },
            )
            # Email content preparation
            message = frappe.render_template(
                "recruitment/public/js/templates/welcome_reminder.html",
                {
                    "job": job,
                    "joining_date": joining_date,
                    "location": job.custom_location,
                    "hiring_company": job.custom_hiring_company,
                    "company_address": job.custom_company_address,
                },
            )
            subject = f" Welcome to {job['company']} - Joining Details"
            # Send email
            frappe.sendmail(
                recipients=[job["applicant_email"],job['owner']],
                subject=subject,
                message=message,
                attachments=[
                    {
                        "fname": "annexure.pdf",
                        "fcontent": pdf,
                    }
                ],
                reference_doctype="Job Offer",
                reference_name=job["name"],
                now=True,
            )
        except Exception as e:
            # Log errors
            frappe.log_error(
                f"Error sending email for Job Offer {job['name']}: {str(e)}",
                "Job Offer Reminder Error",
            )


@frappe.whitelist()
def job_applicant_update_status(doc, method=None):
    if doc.workflow_state == "Approved":
        frappe.db.set_value(
            "Job Applicant", doc.job_applicant, "status", "Offer Released"
        )


@frappe.whitelist()
def job_applicant_update_status_after_approve(doc, method=None):
    if doc.workflow_state == "Offer Accepted":
        frappe.db.set_value(
            "Job Applicant", doc.job_applicant, "status", "Offer Accepted"
        )
    elif doc.workflow_state == "Offer Declined":
        frappe.db.set_value(
            "Job Applicant", doc.job_applicant, "status", "Offer Declined"
        )


@frappe.whitelist()
def handle_workflow_action_for_job_offer(doc_name, action=None, reason=None):
    """
    Handles workflow actions for Job Requisition, including sending emails using templates.

    Args:
        doc_name (str): Name of the Job Requisition document.
        action (str): Action performed in the workflow ("approve" or "reject").
        reason (str, optional): Reason for rejection (if applicable).
    """
    try:
        # Fetch the Job Requisition document
        doc = frappe.get_doc("Job Offer", doc_name)
        # Define the template name based on the action
        if action == "pending_approval_from_director":
            rendered_content = frappe.render_template(
                "recruitment/public/js/templates/internal_document.html", {"doc": doc}
            )
            subject = "Job Offer Approval"
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
                <div class="header">Job Offer Approval</div>
                <div class="content">
                    <p>Dear Sir/Ma'am,</p>
                    <p>A new job offer has been Created and requires your approval. Below are the details:</p>
                     
                    <ul>
                        <li><strong>Applicant Name:</strong> {doc.applicant_name}</li>
                        <li><strong>Job Title:</strong> {doc.designation}</li>
                        <li><strong>Department:</strong> {doc.custom_department}</li>
                        <li><strong>Job Offer ID:</strong> {doc.name}</li>
                    </ul>

                    <p>Please click the link below to approve or reject the request:</p>
                    <p><a href="{frappe.utils.get_url_to_form(doc.doctype, doc.name)}">View Job Offer</a></p>
                    <p>Thank you for your prompt attention.</p>

                    {rendered_content}
                </div>
                <div class="footer">
                    <p>Best regards,</p>
                    <p>Recruiter Team</p>
                </div>
            </body>
            </html>
            """
        elif action == "reject":
            subject = "Job Offer Rejected"
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
                <div class="header">Job Offer Rejected</div>
                <div class="content">
                    <p>Dear {frappe.db.get_value("User",doc.owner,'full_name')},</p>
                    <p>Job Offer {doc.name} has been rejected</p>
                    <p>Reason : {reason} </p>
                    <p>Please contact the director for further clarification.</p>
                   
                </div>
            </body>
            </html>
            """
            # Save the rejection reason in the document
            doc.custom_remark = reason
            doc.save()
        elif action == "on_hold":
            subject = "Job Offer On Hold"
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
                <div class="header">Job Offer On Hold</div>
                <div class="content">
                    <p>Dear {frappe.db.get_value("User",doc.owner,'full_name')},</p>
                    <p>Job Offer {doc.name} has been On Hold</p>
                    <p>Reason : {reason} </p>
                    <p>Please contact the director for further clarification.</p>
                   
                </div>
            </body>
            </html>
            """
            # Save the rejection reason in the document
            doc.custom_remark = reason
            doc.save()
        elif action == "pending_approval_from_tl":
            subject = "Job Offer Pending Approval - Team Lead"

            # Render the HTML template with the job offer details
            rendered_content = frappe.render_template(
                "recruitment/public/js/templates/internal_document.html", {"doc": doc}
            )

            # Append the rendered content to the email message
            message = f"""
            <p>Dear Sir/Ma'am,</p>
            <p>A new job offer requires your approval. Below are the details:</p>
            <p>Please click the link below to approve or reject the request:</p>
            <p><a href="{frappe.utils.get_url_to_form(doc.doctype, doc.name)}">View Job Offer</a></p>
            {rendered_content}
            """
        attachments = []

        attachment_fields = [
            "resume_attachment",
            "custom_r1_feedback",
            "custom_job_description",
            "custom_r2_feedback",
            "custom_aadhar_card",
            "custom_r3_feedback",
            "custom_other_document",
        ]

        # Process each attachment field
        for field in attachment_fields:
            file_url = doc.get(field)
            if file_url:
                file_path = (
                    frappe.get_site_path("private", file_url.replace("/private/", ""))
                    if "/private/" in file_url
                    else frappe.get_site_path(
                        "public", "files", file_url.replace("/files/", "")
                    )
                )
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        file_content = f.read()
                    attachments.append(
                        {
                            "fname": os.path.basename(file_url),
                            "fcontent": file_content,
                        }
                    )

        # Send the email
        frappe.sendmail(
            recipients=get_users_with_role("Team Lead - Talent Acquisition")
            if action != "pending_approval_from_director"
            else [doc.custom_offer_approver,doc.owner],
            subject=subject,
            message=message,
            reference_doctype="Job Offer",
            reference_name=doc_name,
            attachments=attachments
            if action in ["pending_approval_from_director", "pending_approval_from_tl"]
            else [],
            now=True,
        )
    except Exception as e:
        # Log the error and show a user-friendly message
        frappe.log_error(
            f"Error handling workflow action: {str(e)}", "Workflow Action Error"
        )
        frappe.throw("Unable to process the workflow action. Please check the logs.")


def send_scheduled_emails_for_job_offer():
    """
    Sends pending workflow emails that were scheduled.
    """
    try:
        now = now_datetime()
        # Fetch all Job Applicants where email is pending and scheduled time has passed
        pending_emails = frappe.get_all(
            "Job Offer",
            filters={
                "custom_email_status": "Pending",
                "custom_email_schedule_time": ["<=", now],
            },
            fields=[
                "name",
                "applicant_email",
                "status",
                "applicant_email",
                "custom_email_schedule_time",
            ],
        )
        for job_offer in pending_emails:
            doc = frappe.get_doc("Job Offer", job_offer.name)
            context = {"doc": doc}
            subject = frappe.render_template(
                frappe.get_doc(
                    "Email Template",
                    "Submission of Resignation Email & Acceptance Letter",
                ).subject,
                context,
            )
            message = frappe.render_template(
                frappe.get_doc(
                    "Email Template",
                    "Submission of Resignation Email & Acceptance Letter",
                ).response,
                context,
            )
            frappe.sendmail(
                recipients=[doc.applicant_email,doc.owner],
                subject=subject,
                message=message,
                reference_doctype="Job Offer",
                reference_name=doc.name,
                cc=get_users_with_role("Team Lead - Talent Acquisition"),
                expose_recipients="header",
                now=True,
            )
            doc.db_set("custom_email_status", "Sent")
            doc.save()
        return f"Processed {len(pending_emails)} pending emails."
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Scheduled Email Processing Error")


@frappe.whitelist()
def create_notification_log_for_job_offer_flow(docname):
    job_offer_doc = frappe.get_doc("Job Offer", docname)
    user_name = frappe.db.get_value("User", job_offer_doc.owner, "full_name")

    workflow_notifications = {
        "Approval Pending By Team Lead- Talent Acquisition": {
            "roles": ["Team Lead - Talent Acquisition"],
            "message": f"Job Offer {job_offer_doc.name} has been created by {user_name} and is pending your review.",
            "subject": f"Pending Approval: Job Offer {job_offer_doc.name}",
        },
        "Approval Pending By Manager Talent Acquisition": {
            "roles": ["Manager - Talent Acquisition", "Team Lead - Talent Acquisition"],
            "extra_users": [job_offer_doc.owner],
            "message": f"Job Offer {job_offer_doc.name} has been approved by {user_name} and is pending your review.",
            "subject": f"Pending Approval: Job Offer {job_offer_doc.name}",
        },
        "Approved"
        or "Approval Pending By Director": {
            "roles": ["Team Lead - Talent Acquisition", "Manager - Talent Acquisition"],
            "extra_users": [job_offer_doc.owner],
            "message": f"Job Offer {job_offer_doc.name} has been approved.",
            "subject": f"Job Offer {job_offer_doc.name} Approved",
        },
        "Rejected": {
            "roles": ["Team Lead - Talent Acquisition", "Manager - Talent Acquisition"],
            "extra_users": [job_offer_doc.owner],
            "message": f"Job Offer {job_offer_doc.name} has been rejected.",
            "subject": f"Job Offer {job_offer_doc.name} Rejected",
        },
        "On Hold": {
            "roles": ["Team Lead - Talent Acquisition", "Manager - Talent Acquisition"],
            "extra_users": [job_offer_doc.owner],
            "message": f"Job Offer {job_offer_doc.name} has been put on hold.",
            "subject": f"Job Offer {job_offer_doc.name} On Hold",
        },
    }
    # Fetch details for the current workflow state
    notification = workflow_notifications.get(job_offer_doc.workflow_state)
    if not notification:
        return  # No matching workflow state found, exit function

    # Collect unique users based on roles and extra users
    users = set()
    for role in notification.get("roles", []):
        users.update(get_users_with_role(role))
    users.update(notification.get("extra_users", []))
    # Send notifications
    for user in users:
        create_notification_log(
            notification["subject"],
            notification["message"],
            "Alert",
            "Job Offer",
            job_offer_doc.name,
            user,
        )
