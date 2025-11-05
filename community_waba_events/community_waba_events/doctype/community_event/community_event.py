# Copyright (c) 2025, Manqala Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CommunityEvent(Document):
    def validate(self):
        self.ensure_unique_items()
        self.ensure_unique_admins()

    def validate_update_after_submit(self):
        self.ensure_unique_items()
        self.ensure_unique_admins()

    def ensure_unique_items(self):
        seen = set()
        for row in self.items or []:
            item = row.item or ""
            participant_type = row.participant_type or ""
            key = (item, participant_type)
            if key in seen:
                frappe.throw(
                    f"Duplicate item in 'Items' row {row.idx}: {item=!r}, {participant_type=!r}"
                )
            seen.add(key)

    def ensure_unique_admins(self):
        seen = set()
        for row in self.admins or []:
            user = row.user or ""
            if user in seen:
                frappe.throw(f"Duplicate item in 'Admins' row {row.idx}: {user=!r}")
            seen.add(user)
