frappe.ui.form.on("Job Applicant", "create_custom_buttons")
frappe.ui.form.on("Job Applicant", {
    before_save: function(frm) {
        if (frm.skip_duplicate_check) {
            frm.skip_duplicate_check = false;
            return;
        }
        if (frm.is_new()) {
            frappe.validated = false;
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Job Applicant",
                    filters: {
                        designation: frm.doc.designation,
                        custom_department: frm.doc.custom_department,
                        email_id: frm.doc.email_id,
                        custom_hiring_company: frm.doc.custom_hiring_company,
                        job_title: frm.doc.job_title,
                        status: ['in', [
                            'Not Shortlisted',
                            'R1 Rejected',
                            'R2 Rejected',
                            'R3 Rejected',
                            'Final Rejected',
                            'No Show',
                            'Candidate Backed Out'
                        ]]
                    },
                    fieldname: "name"
                },
                callback: function(response) {
                    if (response.message && response.message.name) {
                        frappe.confirm(
                            `A Job Applicant for <b>${frm.doc.designation}</b> with Hiring Company <b>${frm.doc.custom_hiring_company}</b> in Department <b>${frm.doc.custom_department}</b> already exists.<br><br>Do you still want to save this record?`,
                            function() {
                                frm.skip_duplicate_check = true; 
                                frm.save(); 
                            },
                            function() {}
                        );
                    } else {
                        frappe.validated = true;
                    }
                }
            });
        }
    },
    refresh: function(frm) {
        if (['Not Shortlisted', 'Profile Under Review','Draft','Send to Team Leader'].includes(frm.doc.status)) {
            $('.row.form-dashboard-section.form-links').hide();
        }
        if ((frm.doc.status === "R2 Selected" || frm.doc.status === "R3 Selected") && frm.doc.custom_send_document_request_email == 0 && frappe.user.has_role('Talent Acquisition Executive')) {
            frm.add_custom_button(__('Send Document Request'), function() {
                frappe.call({
                    method: "recruitment.backend_code.job_applicant.job_applicant.send_document_request",
                    args: {
                        applicant: frm.doc.applicant_name,
                        applicant_email: frm.doc.email_id,
                        name: frm.doc.name,
                        hiring_company: frm.doc.custom_hiring_company,
                        position: frm.doc.custom_position
                    },
                    callback: function(r) {
                        frm.remove_custom_button(__('Send Document Request'));
                    }
                });
            })
        }
        if (frm.doc.status === "R2 Selected" || frm.doc.status === "R3 Selected") {
            frm.add_custom_button(__('Create Job Offer'), function() {
                frappe.db.get_value(
                    "Job Offer", {
                        job_applicant: frm.doc.name
                    },
                    "name",
                    (r) => {
                        if (r?.name) {
                            frappe.set_route("Form", "Job Offer", r.name)
                        } else {
                            frappe.model.open_mapped_doc({
                                method: "recruitment.backend_code.job_applicant.job_applicant.create_job_offer",
                                frm: frm,
                                callback: function(new_doc) {
                                    // Ensure the document is created before setting the field value
                                    console.log(new_doc)
                                    frappe.model.trigger("custom_hiring_company", new_doc.name, frm.doc.custom_hiring_company);
                                }
                            })
                        }
                    })
            })
        }
    },
    create_custom_buttons: function(frm) {
        if (!frm.doc.__islocal && ['Shortlisted','R1 Selected','R2 Selected'].includes(frm.doc.status)) {
            frm.add_custom_button(
                __("Interview"),
                function() {
                    frm.events.create_dialog(frm);
                },
                __("Create"),
            );
        }
        if (!frm.doc.__islocal && frm.doc.status == "Accepted") {
            if (frm.doc.__onload && frm.doc.__onload.job_offer) {
                $('[data-doctype="Employee Onboarding"]').find("button").show();
                $('[data-doctype="Job Offer"]').find("button").hide();
                frm.add_custom_button(
                    __("Job Offer"),
                    function() {
                        frappe.set_route("Form", "Job Offer", frm.doc.__onload.job_offer);
                    },
                    __("View"),
                );
            } else {
                $('[data-doctype="Employee Onboarding"]').find("button").hide();
                $('[data-doctype="Job Offer"]').find("button").show();
                frm.add_custom_button(
                    __("Job Offer"),
                    function() {
                        frappe.route_options = {
                            job_applicant: frm.doc.name,
                            applicant_name: frm.doc.applicant_name,
                            designation: frm.doc.job_opening || frm.doc.designation,
                        };
                        frappe.new_doc("Job Offer");
                    },
                    __("Create"),
                );
            }
        }
    },
    job_title: function(frm) {
        frappe.model.get_value(
            'Job Opening',
            frm.doc.job_title,
            'custom_job_description_for_candidate',
            function(r) {
                console.log(r)
                frm.set_value("description", r.custom_job_description_for_candidate)
            }
        );
    },
    status: function(frm) {
        if (frm.doc.status === "Shortlisted" || frm.doc.status == 'Not Shortlisted') {
            frappe.confirm(
                __("Are you sure you want to shortlist this applicant?"),
                function() {
                    let now = new Date();
                    // Add 6 hours to the current time
                    now.setHours(now.getHours() + 6);
                    // Format the date to MySQL-compatible format: YYYY-MM-DD HH:MM:SS
                    let scheduled_time = now.getFullYear() + "-" +
                        String(now.getMonth() + 1).padStart(2, '0') + "-" +
                        String(now.getDate()).padStart(2, '0') + " " +
                        String(now.getHours()).padStart(2, '0') + ":" +
                        String(now.getMinutes()).padStart(2, '0') + ":" +
                        String(now.getSeconds()).padStart(2, '0');
                    frm.set_value("custom_email_status", "Pending");
                    frm.set_value("custom_email_scheduled_time", scheduled_time);
                    frm.save();
                }
            );
        }
        if (frm.doc.status == 'Not Shortlisted' && frm.doc.custom_email_status == 'Sent') {
            frm.set_value("custom_email_status", "Pending");
            frm.save();
        }
    }
})