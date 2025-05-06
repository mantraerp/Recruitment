// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
frappe.ui.form.off('Interview', 'add_custom_buttons')
frappe.ui.form.off('Interview', 'submit_feedback')
frappe.ui.form.off('Interview', 'show_feedback_dialog')
frappe.ui.form.off('Interview', 'get_fields_for_feedback')
frappe.ui.form.off("Interview", "show_reschedule_dialog")
frappe.ui.form.on("Interview", {
    refresh: function(frm) {
        if (frm.doc.status == 'On Hold') {
            frm.set_df_property('status', 'allow_on_submit', 1)
        } else {
            frm.set_df_property('status', 'allow_on_submit', 0)
        }
        if (frm.doc.docstatus == 1) {
            frm.set_df_property("interview_details", "cannot_add_rows", true);
        }
        if (frm.doc.docstatus == 0 && frm.doc.status == 'Pending') {
            frm.add_custom_button(
                __("Cancel Document"),
                function() {
                    frappe.confirm(
                        __("Are you sure you want to forcefully cancel this document?"),
                        function() {
                            frappe.call({
                                method: "recruitment.backend_code.interview.interview.send_interview_cancellation_notification",
                                args: {
                                    docname: frm.doc.name,
                                },
                                callback: function(r) {
                                    if (!r.exc) {
                                        frappe.msgprint(__("Document has been forcefully cancelled."));
                                        frm.reload_doc(); // Refresh form
                                    }
                                }
                            });
                        }
                    );
                },
            );
        }
    },
    add_custom_buttons: async function(frm) {
        if (frm.doc.docstatus === 2 || frm.doc.__islocal) return;
        if (frm.doc.status === "Pending") {
            frm.add_custom_button(
                __("Reschedule Interview"),
                function() {
                    frm.events.show_reschedule_dialog(frm);
                    frm.refresh();
                },
                __("Actions"),
            );
        }
        const has_submitted_feedback = await frappe.db.get_value(
            "Interview Feedback", {
                interviewer: frappe.session.user,
                interview: frm.doc.name,
                interview_round: frm.doc.interview_round,
                docstatus: [
                    "!=", 2
                ]
            },
            "name",
        );
        console.log(has_submitted_feedback.message?.name)
        if (has_submitted_feedback.message?.name) return;
        const allow_feedback_submission = frm.doc.interview_details.some(
            (interviewer) => interviewer.interviewer === frappe.session.user,
        );
        if (allow_feedback_submission) {
            frm.page.set_primary_action(__("Submit Feedback"), () => {
                frm.trigger("submit_feedback");
            });
        }
    },
    show_feedback_dialog: function(frm, data) {
        let fields = frm.events.get_fields_for_feedback();
        let criteria = frm.events.get_fields_for_feeback_for_non_criteria();
        let d = new frappe.ui.Dialog({
            title: __("Submit Feedback"),
            fields: [{
                    fieldname: "skill_set",
                    fieldtype: "Table",
                    label: __("Skill Assessment"),
                    cannot_add_rows: false,
                    in_editable_grid: true,
                    reqd: 1,
                    fields: fields,
                    data: data.expected_skills,
                },
                {
                    fieldname: "criteria",
                    fieldtype: "Table",
                    label: __("Non Rated Criteria"),
                    cannot_add_rows: false,
                    in_editable_grid: true,
                    reqd: 1,
                    fields: criteria,
                    data: data.non_criteria_skills,
                },
                {
                    fieldname: "result",
                    fieldtype: "Select",
                    options: ["", "Selected", "Rejected"],
                    label: __("Result"),
                    reqd: 1,
                },
                {
                    fieldname: "feedback",
                    fieldtype: "Small Text",
                    label: __("Feedback"),
                },
                {
                    fieldname: "final_feedback",
                    fieldtype: "Small Text",
                    label: __("Final Comment and Recommedation"),
                }
            ],
            size: "large",
            minimizable: true,
            static: true,
            primary_action: function(values) {
                frappe
                    .call({
                        method: "recruitment.backend_code.interview.interview.create_interview_feedback",
                        args: {
                            data: values,
                            interview_name: frm.doc.name,
                            interviewer: frappe.session.user,
                            job_applicant: frm.doc.job_applicant,
                        },
                    })
                    .then(() => {
                        frm.refresh();
                    });
                d.hide();
            },
        });
        d.show();
        d.get_close_btn().show();
    },
    get_fields_for_feedback: function() {
        return [{
                fieldtype: "Link",
                fieldname: "skill",
                options: "Skill",
                in_list_view: 1,
                label: __("Skill"),
            },
            {
                fieldtype: "Rating",
                fieldname: "rating",
                label: __("Rating"),
                in_list_view: 1,
                reqd: 1,
            },
            {
                fieldtype: "Small Text",
                fieldname: "comment",
                label: __("Comment"),
                in_list_view: 1,
            },
        ];
    },
    get_fields_for_feeback_for_non_criteria: function() {
        return [{
                fieldtype: "Data",
                fieldname: "criteria",
                in_list_view: 1,
                label: __("Skill"),
            },
            {
                fieldtype: "Data",
                fieldname: "description",
                label: __("Description"),
                in_list_view: 1,
                reqd: 1,
            },
            {
                fieldtype: "Small Text",
                fieldname: "comment",
                label: __("Comment"),
                in_list_view: 1
            }
        ];
    },
    submit_feedback: function(frm) {
        frappe.call({
            method: "recruitment.backend_code.interview.interview.get_expected_skill_set",
            args: {
                interview_round: frm.doc.interview_round,
            },
            callback: function(r) {
                frm.events.show_feedback_dialog(frm, r.message);
                frm.refresh();
            },
        });
    },
    handle_interview_evaluation_form_action: function(frm, action) {
        frappe.call({
            method: "recruitment.backend_code.interview.interview.make_interview_evaluation_form",
            args: {
                source_name: frm.doc.name,
            },
            callback: function(r) {
                const byteCharacters = atob(r.message); // Decode base64
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) {
                    byteNumbers[i] = byteCharacters.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                const blob = new Blob([byteArray], {
                    type: "application/pdf"
                });
                // Create a download link
                const link = document.createElement("a");
                link.href = window.URL.createObjectURL(blob);
                link.download = `interview_feedback_${frm.doc.name}.pdf`;
                link.click();
                // Clean up the URL object
                window.URL.revokeObjectURL(link.href);
            }
        });
    },
    show_reschedule_dialog: function(frm) {
        let d = new frappe.ui.Dialog({
            title: "Reschedule Interview",
            fields: [{
                    label: "Schedule On",
                    fieldname: "scheduled_on",
                    fieldtype: "Date",
                    reqd: 1,
                    default: frm.doc.scheduled_on,
                },
                {
                    label: "From Time",
                    fieldname: "from_time",
                    fieldtype: "Time",
                    reqd: 1,
                    default: frm.doc.from_time,
                },
                {
                    label: "To Time",
                    fieldname: "to_time",
                    fieldtype: "Time",
                    reqd: 1,
                    default: frm.doc.to_time,
                },
            ],
            primary_action_label: "Reschedule",
            primary_action(values) {
                if (values.to_time <= values.from_time) {
                    frappe.msgprint({
                        title: __("Invalid Time Range"),
                        indicator: "red",
                        message: __("The 'To Time' must be greater than the 'From Time'."),
                    });
                    return;
                }
                frm.call({
                    method: "reschedule_interview",
                    doc: frm.doc,
                    args: {
                        scheduled_on: values.scheduled_on,
                        from_time: values.from_time,
                        to_time: values.to_time,
                    },
                }).then(() => {
                    frm.refresh();
                    d.hide();
                });
            },
        });
        d.show();
    },
})