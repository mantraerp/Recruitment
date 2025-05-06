import frappe
def permission_query_condition(user,doctype=None):
    """Returns permission conditions dynamically based on the user's roles and the doctype."""
    user = user or frappe.session.user

    # Allow Administrator full access
    if user == "Administrator":
        return ""

    # Define allowed roles for each doctype
    role_permissions = {
        "Job Opening": ["Manager - Talent Acquisition", "Team Lead - Talent Acquisition"],
        "Job Applicant": ["Talent Acquisition Executive", "Manager - Talent Acquisition", "Team Lead - Talent Acquisition"],
        "Job Requisition": ["Manager - Talent Acquisition", "Hiring Manager","Team Lead - Talent Acquisition","Job Requisition Approver"],
        "Interview":["Team Lead - Talent Acquisition","Talent Acquisition Executive","Manager - Talent Acquisition","Hiring Manager"],
        "Job Offer":["Talent Acquisition Executive", "Manager - Talent Acquisition", "Team Lead - Talent Acquisition","Job Offer Approver","HR OPS User"],
        "Interview Feedback":["Interviewer","Hiring Manager"]
    }

    allowed_roles = role_permissions.get(doctype, [])  # Get allowed roles for the given doctype
    user_roles = frappe.get_roles(user)

    # Grant access if the user has at least one allowed role
    if any(role in user_roles for role in allowed_roles):
        return ""
    if doctype == "Job Applicant":
        return f"""
            (
                job_title IN ( 
                    SELECT name FROM `tabJob Opening` 
                    WHERE custom_hiring_manager = '{user}'
                )
                AND workflow_state = 'Approved'
            )
            OR JSON_CONTAINS(_assign, '\"{user}\"')
            OR EXISTS (
                SELECT 1 FROM `tabDocShare` ds 
                WHERE ds.share_doctype = 'Job Applicant'
                AND ds.share_name = `tabJob Applicant`.name
                AND ds.user = '{user}'
            )
        """
    if doctype == "Interview":
        return f"""
            EXISTS (
                SELECT 1 FROM `tabInterview Detail` id 
                WHERE id.parent = `tabInterview`.name
                AND id.interviewer = '{user}'
            )
            OR JSON_CONTAINS(_assign, '\"{user}\"')
            OR EXISTS (
                SELECT 1 FROM `tabDocShare` ds 
                WHERE ds.share_doctype = 'Interview'
                AND ds.share_name = `tabInterview`.name
                AND ds.user = '{user}'
            )
        """
    if doctype == "Job Opening":
        return f"""
            custom_hiring_manager = '{user}'
            OR JSON_CONTAINS(_assign, '\"{user}\"')
            OR EXISTS (
                SELECT 1 FROM `tabDocShare` ds 
                WHERE ds.share_doctype = 'Job Opening'
                AND ds.share_name = `tabJob Opening`.name
                AND ds.user = '{user}'
            )
            """
    assigned_condition = f"JSON_CONTAINS(_assign, '\"{user}\"')"
    shared_condition = f"""
        EXISTS (
            SELECT 1 FROM `tabDocShare` ds 
            WHERE ds.share_doctype = '{doctype}'
            AND ds.share_name = `tab{doctype}`.name
            AND ds.user = '{user}'
        )
    """

    # Restrict access if the user does not have any allowed role
    return f"({assigned_condition} OR {shared_condition})"


def has_permission(doc, user):
    """Checks if the user has permission to view a specific record dynamically based on its doctype."""
    user = user or frappe.session.user

    # Allow Administrator full access
    if user == "Administrator":
        return True

    # Allow access to new records
    if doc.is_new():
        return True

    condition = permission_query_condition(user,doc.doctype) or "1=1"

    query = f"""
        SELECT name 
        FROM `tab{doc.doctype}`
        WHERE ({condition}) AND name = %s
    """
    
    doc_list = frappe.db.sql(query, (doc.name,))
    
    return bool(doc_list)
