frappe.ui.form.ControlAttach.prototype.on_upload_complete = async function (attachment) {
    if (this.frm) {
        await this.parse_validate_and_set_in_model(attachment.file_url);
        this.frm.attachments.update_attachment(attachment);

       
        if (this.frm.doctype !== "Job Applicant") {
            this.frm.doc.docstatus == 1 ? this.frm.save("Update") : this.frm.save();
        }
    }
    this.set_value(attachment.file_url);
};


frappe.ui.form.ControlAttach.prototype.clear_attachment = function () {
    let me = this;
    if (this.frm) {
        me.parse_validate_and_set_in_model(null);
        me.refresh();
        me.frm.attachments.remove_attachment_by_filename(me.value, async () => {
            await me.parse_validate_and_set_in_model(null);
            me.refresh();

            if (me.frm.doctype !== "Job Applicant") {
                me.frm.doc.docstatus == 1 ? me.frm.save("Update") : me.frm.save();
            }
        });
    } else {
        this.dataurl = null;
        this.fileobj = null;
        this.set_input(null);
        this.parse_validate_and_set_in_model(null);
        this.refresh();
    }
};