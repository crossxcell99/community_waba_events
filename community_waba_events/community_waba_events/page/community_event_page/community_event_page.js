frappe.pages['community-event-page'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Events',
        single_column: true
    });

    // The actual controller
    wrapper.events_page = new CommunityEventAdmin(wrapper, page);
};

class CommunityEventAdmin {
    constructor(wrapper, page) {
        this.wrapper = wrapper;
        this.page = page;
        this.body = $(this.page.main);
        this.setup();
        // on route change (e.g. /community-event-page/<event>)
        $(wrapper).bind('show', () => {
            this.refresh();
        });
    }

    setup() {
        // load html5-qrcode script dynamically if not present (use CDN)
        // if (typeof Html5Qrcode === 'undefined') {
        //     $('<script src="https://unpkg.com/html5-qrcode@2.3.7/minified/html5-qrcode.min.js"></script>')
        //         .appendTo('head');
        // }

        // containers
        this.body.empty();
        this.$list = $('<div class="events-list row"></div>').appendTo(this.body);
        this.$event_area = $('<div class="event-area"></div>').appendTo(this.body);

        // small mobile-style layout
        this.page.set_secondary_action('Refresh', () => this.refresh());
    }

    refresh() {
        const route = frappe.get_route();
        // route format: ['community-event-page'] or ['community-event-page', 'EVENT_NAME']
        if (route.length == 1) {
            this.show_events();
        } else {
            const event = decodeURIComponent(route[1]);
            this.show_event_page(event);
        }
    }

    show_events() {
        this.$event_area.empty();
        this.$list.empty();
        frappe.dom.freeze("Fetching");
        frappe.call({
            method: 'community_waba_events.api.get_events',
            callback: (r) => {
                frappe.dom.unfreeze();
                const events = r.message || [];
                if (!events.length) {
                    this.$list.append($('<div class="col-12"><p>No events assigned</p></div>'));
                    return;
                }
                events.forEach(({ name }) => {
                    const $card = $(`
                        <div class="col-12 mb-2">
                          <div class="card item-card" data-name="${name}">
                            <div class="card-body">
                              <h5 class="card-title">${name}</h5>
                              <a class="btn btn-sm btn-primary open-event" href="#">Open</a>
                            </div>
                          </div>
                        </div>
                    `);
                    $card.find('.open-event').on('click', (e) => {
                        e.preventDefault();
                        // route to the event page
                        frappe.set_route('community-event-page', encodeURIComponent(name));
                    });
                    this.$list.append($card);
                });
            },
            error: () => frappe.dom.unfreeze(),
        });
    }

    async show_event_page(event) {
        this.$event_area.empty();
        this.$list.empty();

        const $header = $(`<div class="event-header mb-3">
            <h3>${event}</h3>
            <a class="btn btn-sm btn-secondary" href="#events">Back</a>
        </div>`);
        $header.find('a').on('click', (e) => {
            e.preventDefault();
            frappe.set_route('community-event-page');
        });
        this.$event_area.append($header);

        const $verify = $(`
            <div class="card mb-3">
              <div class="card-body">
                <h5>Verify Participant</h5>
                <p class="small text-muted">'Scan a QR code to verify the participant</p>
                <button class="btn btn-block btn-outline-primary" id="verify-scan">Scan QR</button>
                <div id="verify-result" style="margin-top:10px"></div>
              </div>
            </div>
        `);
        this.$event_area.append($verify);

        $verify.find('#verify-scan').on('click', () => {
            this.open_scanner(async (decoded) => {
                // on success: call server verify
                const $res = $verify.find('#verify-result');
                $res.html('<span class="text-muted">Checking...</span>');
                try {
                    frappe.dom.freeze("Verifying");
                    const r = await frappe.call({
                        method: 'community_waba_events.api.verify_participant',
                        args: { event, virtual_id: decoded }
                    });
                    if (r && r.message && r.message.ok) {
                        $res.html(`<div class="text-success">${r.message.data}</div>`);
                    } else {
                        const msg = (r && r.message && r.message.message) ? r.message.message : 'Not found';
                        $res.html(`<div class="text-danger">${msg}</div>`);
                    }
                } finally {
                    frappe.dom.unfreeze();
                }
            });
        });

        // Provide a Service section
        const $provide = $(`
            <div class="card mb-3">
              <div class="card-body">
                <h5>Distribute an Item</h5>
                <div class="form-group" id="item-select-wrap"></div>
                <div class="form-group">
                  <label>Virtual ID</label>
                  <div class="input-group">
                    <input id="virtual-id-input" class="form-control" placeholder="Enter or scan virtual id"/>
                    <div class="input-group-append">
                      <button id="scan-id-btn" class="btn btn-outline-secondary">Scan</button>
                    </div>
                  </div>
                </div>
                <div class="text-right">
                  <button id="submit-provide" class="btn btn-primary">Submit</button>
                </div>
              </div>
            </div>
        `);
        this.$event_area.append($provide);

        // Render a searchable Link control for Service (frappe Link control)
        const $svcWrap = $provide.find('#item-select-wrap');
        // use frappe control factory
        this.item_control = frappe.ui.form.make_control({
            parent: $svcWrap,
            df: {
                label: 'Item',
                fieldname: 'item_select',
                fieldtype: 'Link',
                options: 'Community Event Item',
                get_query: function(...args) {
                    console.log("get_query args:: ", args);
                    return {
                        filters: { event },
                        query: "community_waba_events.api.get_event_items"
                    };
                },
                reqd: 1
            },
            render_input: true
        });
        this.item_control.refresh_input();

        // scan button behavior
        $provide.find('#scan-id-btn').on('click', () => {
            this.open_scanner((decoded) => {
                this.$event_area.find('#virtual-id-input').val(decoded);
                $provide.find("#submit-provide").click()
            });
        });

        // submit behavior
        $provide.find('#submit-provide').on('click', () => {
            const item = this.item_control.get_value && this.item_control.get_value();
            const virtual_id = this.$event_area.find('#virtual-id-input').val();
            if (!item) {
                frappe.msgprint('Please select an item');
                return;
            }
            if (!virtual_id) {
                frappe.msgprint("Please enter or scan a participant's virtual id");
                return;
            }
            frappe.confirm(
                `Are you sure you want to distribute this item for ${virtual_id}?`,
                async () => {
                    try {
                        frappe.dom.freeze("Submitting");
                        await frappe.call({
                            method: 'community_waba_events.api.distribute_item',
                            args: { event, item, virtual_id },
                            callback: (r) => {
                                if (r.message) {
                                    frappe.show_alert({message: 'Service recorded', indicator: 'green'});
                                } else {
                                    frappe.msgprint(`Request Failed: ${JSON.stringify(r.message)}`);
                                }
                            }
                        });
                    } finally {
                        frappe.dom.unfreeze();
                    }
                }
            );
        });
    }

    open_scanner(on_success) {
        // Create modal overlay
        const $overlay = $(`
            <div class="qr-overlay">
                <div class="qr-wrap">
                    <div id="qr-reader" style="width:100%"></div>
                    <div class="text-right" style="margin-top:6px">
                        <button class="btn btn-sm btn-secondary" id="close-qr">Close</button>
                    </div>
                </div>
            </div>
        `).appendTo('body');

        const stopAndClose = (html5QrCode) => {
            if (html5QrCode) {
                console.log(">>> ", { html5QrCode })
                html5QrCode.stop().catch(() => {}).then(()=> {
                    html5QrCode.clear().catch(()=>{});
                });
            }
            $overlay.remove();
        };

        // Wait for html5-qrcode to be available
        const waitForLib = (cb) => {
            if (typeof Html5Qrcode !== 'undefined') cb();
            else setTimeout(()=>waitForLib(cb), 200);
        };

        waitForLib(() => {
            const html5QrCode = new Html5Qrcode("qr-reader");
            const config = { fps: 10, qrbox: { width: 250, height: 250 } };
            html5QrCode.start(
                { facingMode: { exact: "environment" } }, // prefer back camera
                config,
                (decodedText, decodedResult) => {
                    // decodedText is the content of the QR (we expect virtual id)
                    on_success(decodedText);
                    stopAndClose(html5QrCode);
                },
                (errorMessage) => {
                    // ignore keep scanning
                }
            ).catch(err => {
                // fallback to more permissive camera constraint
                html5QrCode.start({ facingMode: "environment" }, config,
                    (decodedText) => { on_success(decodedText); stopAndClose(html5QrCode); },
                    () => {}
                ).catch(e => {
                    frappe.msgprint(`Unable to access camera: ${e.message}`);
                    $overlay.remove();
                });
            });

            $overlay.find('#close-qr').on('click', () => stopAndClose(html5QrCode));
        });
    }
}
