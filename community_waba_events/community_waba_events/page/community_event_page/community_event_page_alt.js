frappe.pages['community-event-page'] = frappe.pages['community-event-page'] || {};
frappe.pages['community-event-page'].on_page_load = function(wrapper) {
  // build simple app page
  let page = frappe.ui.make_app_page({
    parent: wrapper,
    title: 'Events',
    single_column: true
  });

  wrapper.page = page;
  const root = $('<div/>').attr('id','items-root-inner').appendTo(page.body);
  render_main(root);
};

function render_main(root) {
  root.empty();
  let header = $(`
    <div class="items-header">
      <h2>My Events</h2>
      <button class="btn-large" id="refresh-events">Refresh</button>
    </div>
  `);
  root.append(header);

  let eventContainer = $('<div class="event-list" id="event-list"></div>');
  root.append(eventContainer);

  $('#refresh-events').on('click', function(){ load_events(eventContainer); });

  let route = frappe.get_route();
  if (route && route.length > 1) {
    open_event_page(route[1], root);
  } else {
    load_events(eventContainer);
  }
}

function load_events(container) {
  container.empty();
  const dialog = frappe.show_progress(__('Loading events'), 1, 1);
  frappe.call({
    method: "community_waba_events.services.get_events",
    args: {},
    callback: function(r) {
      container.empty();
      if (!r || !r.message || r.message.length===0) {
        container.append('<div class="text-muted">No events found.</div>');
        frappe.hide_progress();
        return;
      }
      r.message.forEach(function(g) {
        let card = $(`<div class="event-card">
            <div class="left">
              <strong>${frappe.utils.escape_html(g.data || g.name)}</strong>
              <div class="text-muted">${g.item_count || 0} Items</div>
            </div>
            <div class="right">
              <button class="btn-large open-event" data-event="${g.name}">Open</button>
            </div>
          </div>`);
        container.append(card);
      });

      container.find('.open-event').on('click', function() {
        let event = $(this).data('event');
        // navigate to event route
        frappe.set_route('community-event-page', event);
        open_event_page(event, container.closest('#items-root-inner'));
      });

      frappe.hide_progress();
	  dialog.hide();
	  setTimeout(() => dialog.hide(), 500)
    }
  });
}

/* Group page UI */
function open_event_page(event_name, root) {
  root.empty();
  let header = $(`
    <div class="items-header">
      <div style="display:flex; flex-direction:column;">
        <a class="btn-link" id="back-to-events">&larr; Back</a>
        <h2 id="event-title">${frappe.utils.escape_html(event_name)}</h2>
      </div>
      <div style="display:flex; flex-direction:column; gap:6px;">
        <button class="btn-large" id="btn-verify">Verify</button>
      </div>
    </div>
  `);
  root.append(header);
  $('#back-to-events').on('click', function(){
    frappe.set_route('community-event-page');
    render_main(root);
  });

  let itemsList = $('<div class="items-list" id="items-list"></div>');
  root.append(itemsList);

  // load event details
  frappe.call({
    method: "community_waba_events.services.get_event",
    args: { event_name },
    callback: function(r) {
      if (!r.message) {
        frappe.msgprint(__('Failed to load event'));
        return;
      }
      let event = r.message;
      $('#event-title').text(event.name);

      if (event.items.length === 0) {
        itemsList.append('<div class="text-muted">No items configured for this event.</div>');
      } else {
        event.items.forEach(function(s){
          let row = $(`
            <div class="event-item">
              <div>${frappe.utils.escape_html(s.item)}</div>
              <div style="display:flex; gap:8px;">
                <button class="btn-large btn-provide" data-item="${s.item}">Provide</button>
              </div>
            </div>
          `);
          itemsList.append(row);
        });

        itemsList.find('.btn-provide').on('click', function() {
          let itemName = $(this).data('item');
          open_scanner_for_provide(event_name, itemName);
        });
      }
    }
  });

  // verify button scanning only to confirm identity
  $('#btn-verify').on('click', function(){ open_scanner_for_verify(event_name); });
}

/* --- Scanner flows (uses html5-qrcode) --- */

function _create_scanner_overlay() {
  // overlay HTML
  const overlay = $(`
    <div class="scanner-overlay" id="scanner-overlay">
      <div class="scanner-sheet">
        <div id="reader" style="width:100%;"></div>
        <div style="margin-top:8px; display:flex; gap:8px; justify-content:space-between;">
          <input id="manual-input" class="select-item" placeholder="Enter / paste QR text or email" />
          <button class="btn-large" id="manual-submit">Use</button>
        </div>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button class="btn-large" id="close-scanner">Close</button>
        </div>
      </div>
    </div>
  `);

  $('body').append(overlay);
  overlay.find('#close-scanner').on('click', function(){
    overlay.remove();
  });

  return overlay;
}

function _start_html5_qr_scanner(on_scanned, on_error) {
  const readerId = "reader";
  const el = document.getElementById(readerId);
  if (!el) {
    on_error && on_error("No reader element");
    return null;
  }

  // choose qrbox size adaptively
  const maxBox = Math.min(window.innerWidth - 40, 320);
  const qrbox = Math.floor(maxBox);

  const html5QrCode = new Html5Qrcode(readerId, /* verbose= */ false);
  const config = { fps: 10, qrbox: qrbox, experimentalFeatures: { useBarCodeDetectorIfSupported: true } };

  // start camera - prefer environment/back camera
  html5QrCode.start(
    { facingMode: "environment" },
    config,
    (decodedText, decodedResult) => {
      // stop scanner before callback returns
      html5QrCode.stop().then(() => {
        on_scanned(decodedText);
      }).catch((err) => {
        // even if stop fails, still callback
        on_scanned(decodedText);
      });
    },
    (errorMessage) => {
      // ignore frequent decode errors
    }
  ).catch(err => {
    on_error && on_error(err);
  });

  return html5QrCode;
}

function open_scanner_for_verify(event_name) {
  const overlay = _create_scanner_overlay();
  const manualInput = overlay.find('#manual-input');
  const manualSubmit = overlay.find('#manual-submit');

  let scanner = _start_html5_qr_scanner(function(qrtext){
    // when scanned
    overlay.remove();
    verify_and_show(qrtext);
  }, function(err){
    // camera may be blocked — allow manual input
    console.warn('QR scanner error', err);
    frappe.msgprint(__('Camera not available — use manual input'));
  });

  manualSubmit.on('click', function(){
    const txt = manualInput.val().trim();
    if (!txt) return;
    overlay.remove();
    verify_and_show(txt);
    if (scanner) { scanner.stop().catch(()=>{}); }
  });

  overlay.find('#close-scanner').on('click', function(){
    if (scanner) { scanner.stop().catch(()=>{}); }
  });
}

function verify_and_show(qrtext) {
  frappe.call({
    method: "community_waba_events.services.verify_user",
    args: { qr_text: qrtext },
    callback: function(r) {
      const body = r.message;
      if (!body) {
        frappe.msgprint(__('No response from server'));
        return;
      }
      if (!body.ok) {
        frappe.msgprint(__('User not found: ') + (body.reason || ''));
        return;
      }
      // show a friendly toast / dialog
      frappe.msgprint({
        title: __('User verified'),
        message: `<div><strong>${frappe.utils.escape_html(body.full_name)}</strong><div class="text-muted">${frappe.utils.escape_html(body.email || body.user)}</div></div>`
      });
    }
  });
}

function open_scanner_for_provide(event_name, item_name) {
  const overlay = _create_scanner_overlay();
  const manualInput = overlay.find('#manual-input');
  const manualSubmit = overlay.find('#manual-submit');

  let scanner = _start_html5_qr_scanner(function(qrtext){
    overlay.remove();
    confirm_and_call_record(event_name, item_name, qrtext);
  }, function(err){
    console.warn('QR scanner error', err);
    frappe.msgprint(__('Camera not available — use manual input'));
  });

  manualSubmit.on('click', function(){
    const txt = manualInput.val().trim();
    if (!txt) return;
    overlay.remove();
    confirm_and_call_record(event_name, item_name, txt);
    if (scanner) { scanner.stop().catch(()=>{}); }
  });

  overlay.find('#close-scanner').on('click', function(){
    if (scanner) { scanner.stop().catch(()=>{}); }
  });
}

function confirm_and_call_record(event_name, item_name, qrtext) {
  // optional confirmation dialog
  frappe.confirm(
    __('Record that item "{0}" was provided to scanned user?', [item_name]),
    function() {
      frappe.call({
        method: "community_waba_events.services.record_service",
        args: {
          event_name,
          item_name,
          qr_text: qrtext,
          action: "Provide"
        },
        callback: function(r) {
          if (!r.message) {
            frappe.msgprint(__('Failed to call service'));
            return;
          }
          if (!r.message.ok) {
            frappe.msgprint(__('User not found'));
            return;
          }
          frappe.msgprint(__('Service recorded successfully'));
        }
      });
    },
    function() {
      // cancelled
    }
  );
}
