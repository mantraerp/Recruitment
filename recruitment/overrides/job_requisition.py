import frappe
from frappe import _
from hrms.hr.doctype.job_requisition.job_requisition import JobRequisition


class CustomJobRequisition(JobRequisition):
    def validate(self):
        JobRequisition.set_time_to_fill(self)
        self.validate_duplicates()

    def validate_duplicates(self):
        duplicate = frappe.db.exists(
            "Job Requisition",
            {
                "designation": self.designation,
                "department": self.department,
                "status": ("not in", ["Cancelled", "Filled"]),
                "name": ("!=", self.name),
                "custom_requisition_type": self.custom_requisition_type,
                "custom_hiring_company": self.custom_hiring_company,
            },
        )

        if duplicate:
            frappe.throw(
                _(
                    "A Job Requisition for {0} with Hiring Company {1} in Department {2} already exists"
                ).format(
                    frappe.bold(self.designation),
                    frappe.bold(self.custom_hiring_company),
                    frappe.bold(self.department),
                ),
                title=_("Duplicate Job Requisition"),
            )
