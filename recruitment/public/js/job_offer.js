// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
frappe.ui.form.off('Job Offer', 'refresh')
frappe.ui.form.on("Job Offer", {
    onload: function(frm) {
        if (frm.doc.__islocal == 1) {
            frm.trigger('custom_hiring_company')
            frm.trigger('job_applicant')
        }
    },
    custom_employment_type: function(frm) {
        if (['Intern'].includes(frm.doc.custom_employment_type)) {
            frm.set_value('custom_gratuity', 0)
            frm.set_value('custom_nps', 0)
        }
    },
    custom_gratuity: function(frm) {
        if (frm.doc.custom_gratuity) {
            frappe.call({
                method: "recruitment.backend_code.job_offer.job_offer.get_gratuity_value",
                args: {
                    docname: frm.doc.name
                },
                callback: function(response) {
                    frm.set_value('custom_gratuity_amount', response.message.gratuity)
                }
            });
        } else {
            frm.set_value('custom_gratuity_amount', '')
        }
    },
    custom_nps: function(frm) {
        if (frm.doc.custom_nps) {
            frappe.call({
                method: "recruitment.backend_code.job_offer.job_offer.get_gratuity_value",
                args: {
                    docname: frm.doc.name
                },
                callback: function(response) {
                    frm.set_value('custom_nps_amount', response.message.nps)
                }
            });
        } else {
            frm.set_value('custom_nps_amount', '')
        }
    },
    after_workflow_action: function(frm) {
        frappe.call({
            method: "recruitment.backend_code.job_offer.job_offer.create_notification_log_for_job_offer_flow",
            args: {
                docname: frm.doc.name
            }
        });
        if (frm.doc.workflow_state === "Approval Pending By Director") {
            // Call the backend function to handle approval
            frappe.call({
                method: "recruitment.backend_code.job_offer.job_offer.handle_workflow_action_for_job_offer",
                args: {
                    doc_name: frm.doc.name,
                    action: "pending_approval_from_director",
                }
            });
        } else if (frm.doc.workflow_state === "Approval Pending By Team Lead- Talent Acquisition") {
            // Call the backend function to handle approval
            frappe.call({
                method: "recruitment.backend_code.job_offer.job_offer.handle_workflow_action_for_job_offer",
                args: {
                    doc_name: frm.doc.name,
                    action: "pending_approval_from_tl",
                }
            });
        }
    },
    refresh: function(frm) {
        if (
            !frm.doc.__islocal &&
            frm.doc.status == "Accepted" &&
            frm.doc.docstatus === 1 &&
            (!frm.doc.__onload || !frm.doc.__onload.employee)
        ) {
            frm.add_custom_button(__("Create Employee"), function() {
                erpnext.job_offer.make_employee(frm);
            });
        }
        if (frm.doc.__onload && frm.doc.__onload.employee) {
            frm.add_custom_button(__("Show Employee"), function() {
                frappe.set_route("Form", "Employee", frm.doc.__onload.employee);
            });
        }
        if (frappe.user.has_role("HR OPS User") && frm.doc.workflow_state == 'Approved') {
            frm.set_df_property("custom_salary_structure", "allow_on_submit", 1)
        }
        if (
            !frm.doc.__islocal &&
            frm.doc.status == "Offer Accepted" &&
            frm.doc.docstatus === 1 &&
            (!frm.doc.__onload || !frm.doc.__onload.employee)
        ) {
            frm.add_custom_button(__("Create Employee"), function() {
                erpnext.job_offer.make_employee(frm);
            });
        }
        // Always show "Preview Job Offer"
        // Show "Download Job Offer" and "Send Job Offer" only when workflow state is "Approved"
        if (true) {
            const approvedActions = [{
                    label: "Preview Job Offer",
                    trigger: "Preview Job Offer"
                },
                {
                    label: "Download Job Offer",
                    trigger: "download_job_offer"
                },
                {
                    label: "Send Job Offer",
                    trigger: "send_job_offer"
                },
            ];
            if (!(frm.doc.custom_without_department && frm.doc.custom_with_annexure)) {
                approvedActions.forEach(action => {
                    // Show "Send Job Offer" only if workflow state is Approved
                    if ((action.label === "Send Job Offer" || action.label === "Download Job Offer" ) && frm.doc.workflow_state !== "Approved") {
                        return; 
                    }
                    
                    frm.add_custom_button(
                        __(action.label),
                        function() {
                            if (action.label === "Send Job Offer") {
                                frappe.confirm(
                                    "Are you sure you want to send the job offer to the applicant's email?",
                                    function() {
                                        // Yes
                                        frm.events.handle_job_offer_action(frm, action.label);
                                    },
                                    function() {
                                        // No
                                        frappe.msgprint("Sending job offer cancelled.");
                                    }
                                );
                            } else {
                                frm.events.handle_job_offer_action(frm, action.label);
                            }
                        },
                        __("Actions")
                    );
                });
            }
        }
    },
    validate: function(frm) {
        // Validation 1: Date of Joining should not be less than Offer Date
        if (frm.doc.custom_date_of_joining && frm.doc.offer_date) {
            if (frm.doc.custom_date_of_joining < frm.doc.offer_date) {
                frappe.throw(__('The Date of Joining cannot be earlier than the Offer Date.'));
            }
        }
        // Validation 2: Milestone should not be greater than CTC
        if (frm.doc.custom_milestone_value && frm.doc.custom_cost_to_company_ctc) {
            const milestone = parseFloat(frm.doc.custom_milestone_value);
            const ctc = parseFloat(frm.doc.custom_cost_to_company_ctc);
            if (milestone > ctc) {
                frappe.throw(__('The Milestone value cannot be greater than the CTC.'));
            }
        }
    },
    handle_job_offer_action: function(frm, action) {
        frm.call({
            method: 'recruitment.backend_code.job_offer.job_offer.download_job_offer_pdf',
            args: {
                docname: frm.doc.name,
                action: action
            },
            callback: function(r) {
                if (r.message) {
                    if (action === "Preview Job Offer") {
                        var new_window = window.open();
                        new_window.document.write(r.message);
                    } else if (action === "Download Job Offer") {
                        const pdfBase64 = r.message.pdf_base64;
                        const filename = r.message.filename;
                        const link = document.createElement('a');
                        link.href = `data:application/pdf;base64,${pdfBase64}`;
                        link.download = filename;
                        link.click();
                    }
                }
            }
        });
    },
    status: function(frm) {
        if (frm.doc.status === "Offer Accepted") {
            frappe.confirm(
                __("Are you sure you want to update the status as accepted?"),
                function() {
                    let now = new Date();
                    // Add 3 days to the current time
                    now.setDate(now.getDate() + 3);
                    // Format the date to MySQL-compatible format: YYYY-MM-DD HH:MM:SS
                    let scheduled_time = now.getFullYear() + "-" +
                        String(now.getMonth() + 1).padStart(2, '0') + "-" +
                        String(now.getDate()).padStart(2, '0') + " " +
                        String(now.getHours()).padStart(2, '0') + ":" +
                        String(now.getMinutes()).padStart(2, '0') + ":" +
                        String(now.getSeconds()).padStart(2, '0');
                    frm.set_value("custom_email_status", "Pending");
                    frm.set_value("custom_email_schedule_time", scheduled_time);
                    frm.save();
                }
            );
        }
    },
    job_applicant: function(frm) {
        if (frm.doc.job_applicant) {
            frappe.db.get_value(
                "Job Applicant", {
                    name: frm.doc.job_applicant
                },
                "job_title",
                (r) => {
                    frappe.db.get_value(
                        "Job Opening", {
                            name: r.job_title
                        },
                        ["custom_requisition_type", "custom_employee_replacement_name"], (r) => {
                            frm.set_value('custom_recruitment_type', r.custom_requisition_type)
                            frm.set_value('custom_replacement_name', r.custom_employee_replacement_name)
                        })
                }
            );
        } else {
            frm.set_value('custom_recruitment_type', '')
            frm.set_value('custom_replacement_name', '')
        }
    },
    custom_hiring_company: function(frm) {
        const companyAddresses = {
            "Mantra Softech (India) Private Limited": "B-203 Shapath Hexa, Sarkhej - Gandhinagar Hwy, opposite Gujarat High Court, Vishwas City 1, Sola, Ahmedabad, Gujarat 380060",
            "Mefron Technologies (India) Private Limited": "B-703, Shapath Hexa, Nr Ganesh Merediyan Opp. High Court, Sola, Ahmedabad, Gujarat, India, 380060",
            "Mewurk Technologies Private Limited": "B 203 Sapath Hexa Nr Gujarat High Court Opp Kargil Petrol Pump S G Highway Sola, Ahmedabad, Gujarat, India, 380060",
            "Mivanta India Private Limited": "Office No A604 Sapath Hexa, P 50 TP 28 Opp Kargil Petrol Pump S G Highway, Ahmedabad, Gujarat, India, 380060",
            "Mupizo Payments Private Limited": "B-203 Sapath Hexa, Nr. Kargil Petrol Pump, Sola, Ahmedabad, Daskroi, Gujarat, India, 380060",
            "Mocula Optics Technologies Private Limited": "B-203 Sapath Hexa, Nr. Kargil Petrol Pump, Sola, Ahmedabad, Daskroi, Gujarat, India, 380060",
            "Mantra Smart Identity Private Limited": "B1003 Sapath Hexa Nr Gujarat High Court Opp Kargil Petrol Pump S G Highway Sola, Ahmedabad, Gujarat, India, 380060",
            "Mitras Global Private Limited": "B-203, Shapath Hexa, Nr. Gujarat High Court, Sola, Ahmedabad, Daskroi, Gujarat, India, 380060"
        };
        if (frm.doc.custom_hiring_company) {
            frm.set_value('custom_company_address', companyAddresses[frm.doc.custom_hiring_company]);
        } else {
            frm.set_value('custom_company_address', '');
        }
    }
})