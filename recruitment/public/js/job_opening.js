frappe.ui.form.on('Job Opening', {
    department: function(frm) {
        if (frm.doc.department) {
            frm.set_query("custom_hiring_manager", function() {
                return {
                    query: "recruitment.backend_code.job_requisition.job_requisition.get_hiring_managers",
                    filters: {
                        department: frm.doc.department
                    }
                };
            });
            frm.set_query("custom_head_of_department", function() {
                return {
                    query: "recruitment.backend_code.job_requisition.job_requisition.get_head_of_department",
                    filters: {
                        department: frm.doc.department
                    }
                };
            });
        }
    }
});