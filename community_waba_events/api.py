"""extra community apis to create"""

import frappe
import frappe.model
import frappe.model.document


@frappe.whitelist()
def share_contact():
    """creates a virtual id with context set to share_contact"""
    estate = frappe.form_dict.get("estate")
    if not estate:
        raise frappe.ValidationError("estate required")
    property_unit = frappe.form_dict.get("property_unit")
    if not property_unit:
        raise frappe.ValidationError("property_unit required")

    doc = frappe.get_doc(
        {
            "doctype": "Virtual ID",
            "context": "share_contact",
            "estate": estate,
            "property_unit": property_unit,
        }
    )
    doc.insert()
    return doc


def vcard_esc(text: str) -> str:
    """helper to escape characters per vCard rules"""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace("\n", " ")
        .replace(";", r"\;")
        .replace(",", r"\,")
    )


def create_social_activity_score(virtual_id):
    """indicate that the virtual is has been used"""
    docname = virtual_id if isinstance(virtual_id, str) else virtual_id.name
    if frappe.db.exists("Community Event Activity Score", {"reference": docname}):
        return
    doc = (
        virtual_id
        if isinstance(virtual_id, frappe.model.document.Document)
        else frappe.get_doc("Virtual ID", virtual_id)
    )
    score = frappe.get_doc(
        {
            "doctype": "Community Event Activity Score",
            "event": doc.estate,  # the name of the estate is the name of the event
            "participant": doc.owner,  # the the community user
            "score": 1,
            "reference": doc.name,
        }
    )
    score.insert()
    return score


@frappe.whitelist()
def view_contact():
    """downloads contact vcf file for contact with"""

    virtual_id = frappe.form_dict.get("virtual_id")
    if not virtual_id:
        raise frappe.ValidationError("virtual_id required")

    doc = frappe.get_doc("Virtual ID", virtual_id)
    if doc.context != "share_contact":
        raise frappe.ValidationError(
            "contact viewing not permitted for this virtual id"
        )

    user = frappe.get_doc("User", doc.owner)
    first = (user.get("first_name") or "").strip()
    last = (user.get("last_name") or "").strip()
    phone = (user.get("mobile_no") or "").strip() or (user.get("phone") or "").strip()

    if not (first or last or phone):
        raise frappe.ValidationError("No contact information available for linked user")

    create_social_activity_score(doc)

    # Build vCard (VERSION:3.0)
    phone_line = f"TEL;TYPE=CELL:{vcard_esc(phone)}\r\n" if phone else ""
    vcard = (
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        f"N:{vcard_esc(last)};{vcard_esc(first)};;;\r\n"
        f"FN:{vcard_esc((first + ' ' + last).strip())}\r\n"
        f"{phone_line}"
        "END:VCARD\r\n"
    )

    filename = f"{(first or user.name).lower().replace(' ', '_')}.vcf"
    frappe.local.response.filename = filename
    frappe.local.response.filecontent = vcard
    frappe.local.response.type = "download"


@frappe.whitelist(allow_guest=False)
def leaderboard():
    """community event activity leaderboard"""

    event = frappe.form_dict.get("event")
    if not event:
        raise frappe.ValidationError("event required")

    q = frappe.db.sql(
        """
SELECT
    COALESCE( (SELECT SUM(score)
                FROM `tabCommunity Event Activity Score`
                WHERE event = %(event)s AND participant = %(participant)s), 0) AS user_total,
    COALESCE( (SELECT MAX(user_total)
                FROM (SELECT participant, SUM(score) AS user_total
                    FROM `tabCommunity Event Activity Score`
                    WHERE event = %(event)s
                    GROUP BY participant) AS t), 0) AS highest_user_total;
""",
        {"event": event, "participant": frappe.session.user},
        as_dict=1,
    )
    res = q[0]
    return {"score": res.user_total, "highest": res.highest_user_total}


@frappe.whitelist()
def distribute_item():
    """indicate that a participant has received an event item"""

    virtual_id = frappe.form_dict.get("virtual_id")
    if not virtual_id:
        raise frappe.ValidationError("virtual_id required")

    item = frappe.form_dict.get("item")
    if not item:
        raise frappe.ValidationError("item required")

    # TODO: check if user_max exceeded
    # TODO: check if event_max exceeded
    # TODO: create Community Event Item Receipt for user and check max again
    # TODO: return receipt doc
