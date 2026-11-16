/* ==========================================================================
   나라장터 입찰·사전규격 모니터링 대시보드
   - 빌드 없음: data.json 을 fetch 해서 순수 DOM 으로 렌더링
   ========================================================================== */
(function () {
  'use strict';

  var DATA_URL = 'data.json';
  var TZ = 'Asia/Seoul';

  var DATA = null;
  var ITEMS = [];

  var state = {
    kind: 'all',      // all | bid | prespec | other
    region: 'all',    // all | focus | etc
    urgency: 'all',   // all | urgent
    keyword: 'all',
    q: '',
    showExpired: false
  };

  /* ---------------------------------------------------------------- utils */

  function $(sel, root) { return (root || document).querySelector(sel); }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function compact(value) {
    return String(value == null ? '' : value).toLowerCase().replace(/\s+/g, '');
  }

  /** 원 단위 금액 → "2억 5,000만원" 형태 */
  function won(n) {
    if (n == null || isNaN(n)) return '';
    n = Math.abs(Number(n));
    var eok = Math.floor(n / 1e8);
    var man = Math.floor((n % 1e8) / 1e4);
    var out = '';
    if (eok) out += eok.toLocaleString('ko-KR') + '억';
    if (man) out += (out ? ' ' : '') + man.toLocaleString('ko-KR') + '만';
    if (!out) out = n.toLocaleString('ko-KR');
    return out + '원';
  }

  function kstDate(d) {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit'
    }).format(d);
  }

  /** 마감 시각 → 남은 일수 (달력일 기준, KST) */
  function ddayOf(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    var target = Date.parse(kstDate(d) + 'T00:00:00Z');
    var today = Date.parse(kstDate(new Date()) + 'T00:00:00Z');
    return Math.round((target - today) / 86400000);
  }

  function ddayBadge(item) {
    var d = item.dday;
    if (d == null) return '<span class="badge badge--normal">-</span>';
    if (d < 0) return '<span class="badge badge--over">마감</span>';
    var text = d === 0 ? '오늘 마감' : 'D-' + d;
    var cls = d <= 2 ? 'badge--urgent' : (d <= 5 ? 'badge--soon' : 'badge--normal');
    var label = item.kind === 'prespec' ? '의견등록 마감 기준' : '제출 마감 기준';
    return '<span class="badge badge--dday ' + cls + '" title="' + esc(label) + '">' + esc(text) + '</span>';
  }

  function regionBadge(item) {
    var cls = item.region_group === 'focus' ? 'badge--region'
      : (item.region_group === 'nation' ? 'badge--nation' : 'badge--region-out');
    return '<span class="badge ' + cls + '">' + esc(item.region || '기타') + '</span>';
  }

  function kindLabel(kind) {
    return kind === 'bid' ? '입찰공고' : kind === 'prespec' ? '사전규격' : '참고';
  }

  function amountHtml(item) {
    var priceTxt = item.price_est != null ? won(item.price_est) : '';
    var label = item.amount_label || '';
    if (item.price_est != null && item.budget != null) {
      return '<b>' + esc(priceTxt) + '</b><span>기초·배정 ' + esc(won(item.budget)) + '</span>';
    }
    if (item.price_est != null) {
      if (label) {
        if (compact(label).indexOf(compact(priceTxt)) !== -1) {
          return '<b>' + esc(label) + '</b>';
        }
        return '<b>' + esc(priceTxt) + '</b><span>' + esc(label) + '</span>';
      }
      return '<b>' + esc(priceTxt) + '</b><span>' + (item.kind === 'bid' ? '추정가격' : '배정예산') + '</span>';
    }
    return '<b>' + esc(label || '—') + '</b>';
  }

  function amountText(item) {
    var parts = [];
    if (item.price_est != null) parts.push((item.kind === 'bid' ? '추정 ' : '') + won(item.price_est));
    if (item.budget != null) parts.push('기초·배정 ' + won(item.budget));
    if (item.amount_label) {
      var dup = compact(item.price_est != null ? won(item.price_est) : '');
      if (!dup || compact(item.amount_label).indexOf(dup) === -1) parts.push(item.amount_label);
    }
    return parts.length ? parts.join(' / ') : '—';
  }

  function submitHtml(item) {
    if (!item.submit_alert) return esc(item.submit_method || '—');
    return '<span class="alert-text">⚠ ' + esc(item.submit_method || '') + '</span>';
  }

  function sheetKey(item) {
    if (item.sheet_tab) return item.sheet_tab;
    if (item.kind === 'prespec') return 'pre_specs';
    if (item.kind === 'other') return 'others';
    return 'bids';
  }

  function sheetUrl(item) {
    var tabs = (DATA && DATA.sheet && DATA.sheet.tabs) || {};
    var tab = tabs[sheetKey(item)] || tabs.bids;
    if (!tab) return (DATA && DATA.sheet && DATA.sheet.url) || '#';
    return DATA.sheet.url + '#gid=' + tab.gid;
  }

  function keywordLinksHtml(item) {
    var kws = item.keywords || [];
    if (!kws.length) return '';
    var q = encodeURIComponent(kws[0]);
    var path = item.kind === 'prespec' ? '/notices/pre-spec' : '/notices/bid';
    return '<a class="btn btn--ghost" href="https://presignal.co.kr' + path + '?keyword=' + q + '" target="_blank" rel="noopener">키워드 검색</a>';
  }

  /* ------------------------------------------------------------- normalize */

  function normalize(raw, kind) {
    var item = {};
    for (var k in raw) { if (Object.prototype.hasOwnProperty.call(raw, k)) item[k] = raw[k]; }
    item.kind = kind;
    item.kindLabel = kindLabel(kind);
    item.dday = ddayOf(raw.deadline_iso);
    item._hay = compact([raw.title, raw.org, raw.notice_no, raw.region, (raw.keywords || []).join(' ')].join(' '));
    return item;
  }

  function buildItems() {
    ITEMS = []
      .concat((DATA.bids || []).map(function (b) { return normalize(b, 'bid'); }))
      .concat((DATA.pre_specs || []).map(function (b) { return normalize(b, 'prespec'); }))
      .concat((DATA.others || []).map(function (b) { return normalize(b, 'other'); }));
  }

  /* --------------------------------------------------------------- filter */

  function matchBase(item, withKind) {
    if (withKind && state.kind !== 'all' && item.kind !== state.kind) return false;
    if (state.region === 'focus' && item.region_group !== 'focus') return false;
    if (state.region === 'etc' && item.region_group === 'focus') return false;
    if (state.urgency === 'urgent' && !(item.dday != null && item.dday >= 0 && item.dday <= 2)) return false;
    if (state.keyword !== 'all' && (item.keywords || []).indexOf(state.keyword) === -1) return false;
    if (!state.showExpired && item.dday != null && item.dday < 0) return false;
    if (state.q && item._hay.indexOf(compact(state.q)) === -1) return false;
    return true;
  }

  function sortItems(a, b) {
    var ao = a.dday == null ? 1 : (a.dday < 0 ? 2 : 0);
    var bo = b.dday == null ? 1 : (b.dday < 0 ? 2 : 0);
    if (ao !== bo) return ao - bo;
    if (ao === 0 && a.dday !== b.dday) return a.dday - b.dday;
    var ar = a.region_group === 'focus' ? 0 : (a.region_group === 'nation' ? 1 : 2);
    var br = b.region_group === 'focus' ? 0 : (b.region_group === 'nation' ? 1 : 2);
    if (ar !== br) return ar - br;
    return String(a.title).localeCompare(String(b.title), 'ko');
  }

  function visibleItems() {
    return ITEMS.filter(function (it) { return matchBase(it, true); }).sort(sortItems);
  }

  /* --------------------------------------------------------------- render */

  function renderKpi() {
    var bids = ITEMS.filter(function (i) { return i.kind === 'bid' && (i.dday == null || i.dday >= 0); });
    var urgentBids = bids.filter(function (i) { return i.dday != null && i.dday <= 2; });
    var urgentD1 = bids.filter(function (i) { return i.dday === 1; });
    var focus = ITEMS.filter(function (i) { return i.region_group === 'focus' && (i.dday == null || i.dday >= 0); });
    var pres = ITEMS.filter(function (i) { return i.kind === 'prespec' && (i.dday == null || i.dday >= 0); });
    var presUrgent = pres.filter(function (i) { return i.dday != null && i.dday <= 2; });

    var cards = [
      {
        label: '진행 중 입찰',
        value: bids.length + '건',
        sub: '입찰공고 전체 ' + (DATA.bids || []).length + '건 · 마감 전 기준'
      },
      {
        label: 'D-2 이내 임박',
        value: urgentBids.length + '건',
        sub: '입찰공고 기준 · D-1 ' + urgentD1.length + '건 포함',
        urgent: urgentBids.length > 0
      },
      {
        label: '담당 권역',
        value: focus.length + '건',
        sub: (DATA.region_focus_label || '강원·경기·충청·전북') + ' · 전체 항목 중'
      },
      {
        label: '사전규격',
        value: pres.length + '건',
        sub: '의견마감 전 · D-2 이내 ' + presUrgent.length + '건'
      },
      {
        label: '마지막 업데이트',
        value: DATA.updated_label || '—',
        sub: '최신 스캔 ' + ((DATA.scan_basis && DATA.scan_basis.latest_scan) || '—'),
        small: true
      }
    ];

    $('#kpi').innerHTML = cards.map(function (c) {
      return '' +
        '<div class="kpi__card' + (c.urgent ? ' kpi__card--urgent' : '') + '">' +
          '<div class="kpi__label">' + esc(c.label) + '</div>' +
          '<div class="kpi__value' + (c.small ? ' kpi__value--sm' : '') + (c.urgent ? ' kpi__value--urgent' : '') + '">' + esc(c.value) + '</div>' +
          '<div class="kpi__sub">' + esc(c.sub) + '</div>' +
        '</div>';
    }).join('');

    var hint = $('#kpiHint');
    if (hint) {
      hint.textContent = '데이터 기준 ' + (DATA.updated_label || '') +
        ' · D-day는 접속한 날짜로 자동 계산' +
        (DATA.scan_basis ? ' · 11-14~11-16 신규 ' + DATA.scan_basis.new_items + '건 / 정정 ' + DATA.scan_basis.changes + '건' : '');
    }
  }

  function renderWatch() {
    var list = (DATA.watchlist || []);
    $('#watchlist').innerHTML = list.map(function (w) {
      var tone = w.tone === 'urgent' ? 'watch__card--urgent' : 'watch__card--wait';
      var pill = w.tone === 'urgent'
        ? '<span class="badge badge--urgent">' + esc(w.status) + '</span>'
        : '<span class="badge badge--normal">' + esc(w.status) + '</span>';
      var dd = w.deadline_iso
        ? ddayBadge({ dday: ddayOf(w.deadline_iso), kind: 'prespec' })
        : '';
      var links = (w.links || []).map(function (l) {
        return '<a href="' + esc(l.url) + '" target="_blank" rel="noopener">' + esc(l.label) + ' ↗</a>';
      }).join('');
      return '' +
        '<article class="watch__card ' + tone + '">' +
          '<div class="watch__top">' + pill + dd +
            '<span class="watch__label">' + esc(w.label) + '</span>' +
          '</div>' +
          '<div class="watch__meta">' + esc(w.meta) + '</div>' +
          '<div class="watch__note">' + esc(w.note) + '</div>' +
          '<div class="watch__links">' + links + '</div>' +
        '</article>';
    }).join('');
  }

  function renderTabCounts() {
    var counts = { all: 0, bid: 0, prespec: 0, other: 0 };
    ITEMS.forEach(function (it) {
      if (!matchBase(it, false)) return;
      counts.all += 1;
      counts[it.kind] += 1;
    });
    Object.keys(counts).forEach(function (k) {
      var node = $('[data-count="' + k + '"]');
      if (node) node.textContent = counts[k];
    });
    return counts;
  }

  function renderKeywordChips() {
    var map = {};
    ITEMS.forEach(function (it) {
      (it.keywords || []).forEach(function (k) { map[k] = (map[k] || 0) + 1; });
    });
    var keys = Object.keys(map).sort(function (a, b) { return map[b] - map[a]; });
    var html = '<button class="chip' + (state.keyword === 'all' ? ' is-active' : '') + '" type="button" data-keyword="all">키워드 전체</button>';
    html += keys.map(function (k) {
      return '<button class="chip' + (state.keyword === k ? ' is-active' : '') + '" type="button" data-keyword="' + esc(k) + '">' +
        esc(k) + '<span class="chip__n">' + map[k] + '</span></button>';
    }).join('');
    $('#keywordChips').innerHTML = html;
  }

  function renderKeywordStats() {
    var stats = DATA.keyword_stats || [];
    $('#keywordStats').innerHTML = stats.map(function (s) {
      var hasItems = ITEMS.some(function (it) { return (it.keywords || []).indexOf(s.keyword) !== -1; });
      var active = state.keyword === s.keyword ? ' is-active' : '';
      return '<button class="kwstat' + active + '" type="button" data-keyword="' + esc(s.keyword) + '"' +
        (hasItems ? '' : ' disabled') + '>' +
        '<span class="kwstat__head"><span class="kwstat__name">' + esc(s.keyword) + '</span>' +
        '<span class="kwstat__num">입찰 ' + esc(s.bids) + ' · 사전 ' + esc(s.prespec) + '</span></span>' +
        '<span class="kwstat__note">' + esc(s.note) + '</span>' +
        '</button>';
    }).join('');
  }

  function detailHtml(item) {
    return '' +
      '<div class="detail__box">' +
        '<div class="detail__row"><div class="detail__k">접수방식</div><div class="detail__v">' + submitHtml(item) + '</div></div>' +
        '<div class="detail__row"><div class="detail__k">개찰·평가</div><div class="detail__v">' + esc(item.eval_label || '—') + '</div></div>' +
        '<div class="detail__row"><div class="detail__k">계약·평가</div><div class="detail__v">' + esc(item.method || '—') + '</div></div>' +
        '<div class="detail__row"><div class="detail__k">참가자격</div><div class="detail__v">' + esc(item.qualification || '—') + '</div></div>' +
        '<div class="detail__row"><div class="detail__k">체크포인트</div><div class="detail__v">' + esc(item.checkpoint || '—') + '</div></div>' +
        '<div class="detail__actions">' +
          '<a class="btn btn--solid" href="' + esc(item.link) + '" target="_blank" rel="noopener">원문 보기 (presignal)</a>' +
          '<a class="btn btn--ghost" href="' + esc(sheetUrl(item)) + '" target="_blank" rel="noopener">시트에서 보기</a>' +
          keywordLinksHtml(item) +
        '</div>' +
      '</div>';
  }

  function rowHtml(item) {
    var tags = [regionBadge(item),
      '<span class="badge badge--kind">' + esc(item.kindLabel) + '</span>'];
    if (item.relevance === 'low') tags.push('<span class="badge badge--low">관련성 낮음</span>');
    if (item.in_sheet === false) tags.push('<span class="badge badge--unsynced">시트 미기재</span>');

    return '' +
      '<tr class="row' + (item.dday != null && item.dday < 0 ? ' is-over' : '') + '" data-id="' + esc(item.id) + '" tabindex="0" aria-expanded="false">' +
        '<td>' + ddayBadge(item) + '</td>' +
        '<td>' +
          '<div class="cell-title">' + esc(item.title) + '</div>' +
          '<div class="cell-title__sub">' + esc(item.notice_no) + '</div>' +
          '<div class="cell-tags">' + tags.join('') + '</div>' +
        '</td>' +
        '<td class="cell-org">' + esc(item.org || '—') + '</td>' +
        '<td class="cell-amount">' + amountHtml(item) + '</td>' +
        '<td class="cell-deadline">' + esc(item.deadline_label || '—') + '</td>' +
        '<td class="cell-submit">' + submitHtml(item) + '</td>' +
        '<td><div class="cell-check">' + esc(item.checkpoint || item.method || '—') + '</div></td>' +
        '<td><a class="btn btn--solid" href="' + esc(item.link) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">원문</a></td>' +
      '</tr>' +
      '<tr class="detail" data-detail="' + esc(item.id) + '"><td colspan="8">' + detailHtml(item) + '</td></tr>';
  }

  function cardHtml(item) {
    var tags = [ddayBadge(item), regionBadge(item),
      '<span class="badge badge--kind">' + esc(item.kindLabel) + '</span>'];
    if (item.relevance === 'low') tags.push('<span class="badge badge--low">관련성 낮음</span>');
    if (item.in_sheet === false) tags.push('<span class="badge badge--unsynced">시트 미기재</span>');

    var deadlineKey = item.kind === 'prespec' ? '의견마감' : '마감';
    var rows = '' +
      '<div><dt>금액</dt><dd>' + esc(amountText(item)) + '</dd></div>' +
      '<div><dt>' + deadlineKey + '</dt><dd><strong>' + esc(item.deadline_label || '—') + '</strong></dd></div>' +
      '<div><dt>접수</dt><dd>' + submitHtml(item) + '</dd></div>' +
      '<div><dt>평가</dt><dd>' + esc(item.eval_label || '—') + '</dd></div>' +
      '<div><dt>자격</dt><dd>' + esc(item.qualification || '—') + '</dd></div>' +
      '<div><dt>체크</dt><dd>' + esc(item.checkpoint || '—') + '</dd></div>';

    var cls = 'card';
    if (item.dday != null && item.dday < 0) cls += ' card--over';
    else if (item.dday != null && item.dday <= 2) cls += ' card--urgent';

    return '' +
      '<article class="' + cls + '">' +
        '<div class="card__top">' + tags.join('') + '</div>' +
        '<div>' +
          '<h3 class="card__title">' + esc(item.title) + '</h3>' +
          '<p class="card__sub">' + esc(item.notice_no) + '</p>' +
          '<p class="card__org">' + esc(item.org || '—') + '</p>' +
        '</div>' +
        '<dl class="kv">' + rows + '</dl>' +
        '<div class="card__actions">' +
          '<a class="btn btn--solid" href="' + esc(item.link) + '" target="_blank" rel="noopener">원문 보기</a>' +
          '<a class="btn btn--ghost" href="' + esc(sheetUrl(item)) + '" target="_blank" rel="noopener">시트</a>' +
          keywordLinksHtml(item) +
        '</div>' +
      '</article>';
  }

  function renderResult() {
    var items = visibleItems();
    var counts = renderTabCounts();

    $('#tableBody').innerHTML = items.map(rowHtml).join('');
    $('#cards').innerHTML = items.map(cardHtml).join('');

    var empty = $('#empty');
    if (empty) {
      empty.hidden = items.length > 0;
      if (!items.length) {
        var expired = ITEMS.filter(function (it) { return it.dday != null && it.dday < 0; }).length;
        var title = $('#emptyTitle');
        var hint = $('#emptyHint');
        if (!state.showExpired && expired > 0) {
          if (title) title.textContent = '마감 전 항목이 없습니다.';
          if (hint) hint.textContent = '마감이 지난 ' + expired + '건은 위의 "마감 지난 건 표시"를 켜면 볼 수 있습니다. 데이터 기준 ' +
            (DATA.updated_label || '—') + ' — 새 스캔을 반영하려면 data.json 을 갱신하세요.';
        } else {
          if (title) title.textContent = '조건에 맞는 항목이 없습니다.';
          if (hint) hint.textContent = '필터를 풀거나 검색어를 지워 보세요.';
        }
      }
    }
    var tableWrap = $('#tableWrap');
    if (tableWrap) tableWrap.style.display = items.length ? '' : 'none';

    var label = '총 <strong>' + items.length + '</strong>건';
    if (state.kind !== 'all') label += ' · ' + kindLabel(state.kind);
    var conds = [];
    if (state.region === 'focus') conds.push('담당권역');
    if (state.region === 'etc') conds.push('전국·기타');
    if (state.urgency === 'urgent') conds.push('D-2 이내');
    if (state.keyword !== 'all') conds.push('#' + state.keyword);
    if (state.q) conds.push('"' + state.q + '"');
    if (conds.length) label += ' · ' + conds.join(' · ');
    $('#resultCount').innerHTML = label;

    $('#clearFilters').hidden = !(state.kind !== 'all' || state.region !== 'all' ||
      state.urgency !== 'all' || state.keyword !== 'all' || state.q || state.showExpired);

    // 탭 개수 표시 갱신 (renderTabCounts 결과는 counts 로 이미 반영됨)
    void counts;
  }

  function renderAll() {
    renderKpi();
    renderWatch();
    renderKeywordChips();
    renderKeywordStats();
    renderResult();
  }

  function updateToggles() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-kind]'), function (b) {
      var on = b.getAttribute('data-kind') === state.kind;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-region]'), function (b) {
      b.classList.toggle('is-active', b.getAttribute('data-region') === state.region);
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-urgency]'), function (b) {
      b.classList.toggle('is-active', b.getAttribute('data-urgency') === state.urgency);
    });
  }

  /* ---------------------------------------------------------------- events */

  function applyAndRender() {
    updateToggles();
    renderKeywordChips();
    renderKeywordStats();
    renderResult();
    syncUrl();
  }

  function syncUrl() {
    var p = new URLSearchParams();
    if (state.kind !== 'all') p.set('kind', state.kind);
    if (state.region !== 'all') p.set('region', state.region);
    if (state.urgency !== 'all') p.set('urgency', state.urgency);
    if (state.keyword !== 'all') p.set('kw', state.keyword);
    if (state.q) p.set('q', state.q);
    if (state.showExpired) p.set('expired', '1');
    var hash = p.toString();
    try {
      history.replaceState(null, '', hash ? '#' + hash : location.pathname + location.search);
    } catch (e) { /* file:// 등에서 실패해도 무시 */ }
  }

  function readUrl() {
    var raw = (location.hash || '').replace(/^#/, '');
    if (!raw) return;
    var p = new URLSearchParams(raw);
    state.kind = p.get('kind') || 'all';
    state.region = p.get('region') || 'all';
    state.urgency = p.get('urgency') || 'all';
    state.keyword = p.get('kw') || 'all';
    state.q = p.get('q') || '';
    state.showExpired = p.get('expired') === '1';
    var qInput = $('#q');
    if (qInput) qInput.value = state.q;
    var exp = $('#showExpired');
    if (exp) exp.checked = state.showExpired;
  }

  function debounce(fn, ms) {
    var t = null;
    return function () {
      clearTimeout(t);
      t = setTimeout(fn, ms);
    };
  }

  function bindEvents() {
    document.addEventListener('click', function (e) {
      var tab = e.target.closest('[data-kind]');
      if (tab) { state.kind = tab.getAttribute('data-kind'); applyAndRender(); return; }

      var region = e.target.closest('[data-region]');
      if (region) { state.region = region.getAttribute('data-region'); applyAndRender(); return; }

      var urg = e.target.closest('[data-urgency]');
      if (urg) { state.urgency = urg.getAttribute('data-urgency'); applyAndRender(); return; }

      var kw = e.target.closest('[data-keyword]');
      if (kw) {
        var k = kw.getAttribute('data-keyword');
        state.keyword = (state.keyword === k && k !== 'all') ? 'all' : k;
        applyAndRender();
        return;
      }
    });

    var q = $('#q');
    if (q) {
      q.addEventListener('input', debounce(function () {
        state.q = q.value.trim();
        applyAndRender();
      }, 140));
      q.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { q.value = ''; state.q = ''; applyAndRender(); }
      });
    }

    var exp = $('#showExpired');
    if (exp) {
      exp.addEventListener('change', function () {
        state.showExpired = exp.checked;
        applyAndRender();
      });
    }

    var clearBtn = $('#clearFilters');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        state.kind = 'all'; state.region = 'all'; state.urgency = 'all';
        state.keyword = 'all'; state.q = ''; state.showExpired = false;
        if (q) q.value = '';
        if (exp) exp.checked = false;
        applyAndRender();
      });
    }

    // 테이블 행 펼치기 (마우스 + 키보드)
    var tbody = $('#tableBody');
    if (tbody) {
      tbody.addEventListener('click', function (e) {
        var row = e.target.closest('tr.row');
        if (!row) return;
        if (e.target.closest('a')) return;
        toggleRow(row);
      });
      tbody.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var row = e.target.closest('tr.row');
        if (!row) return;
        e.preventDefault();
        toggleRow(row);
      });
    }

    var refresh = $('#refreshBtn');
    if (refresh) {
      refresh.addEventListener('click', function () {
        load(true);
      });
    }
  }

  function toggleRow(row) {
    var id = row.getAttribute('data-id');
    var detail = document.querySelector('tr.detail[data-detail="' + id + '"]');
    if (!detail) return;
    var open = detail.classList.toggle('is-open');
    row.classList.toggle('is-open', open);
    row.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  /* ------------------------------------------------------------------ load */

  function showLoadError(err) {
    var box = $('#loadError');
    var detail = $('#loadErrorDetail');
    if (box) box.hidden = false;
    if (detail) {
      detail.textContent = 'JSON을 읽지 못했습니다 (' + (err && err.message ? err.message : '알 수 없는 오류') +
        '). 브라우저에서 index.html 을 파일로 직접 열면 fetch 가 차단됩니다 — GitHub Pages 주소나 로컬 서버(http://localhost)로 열어 주세요.';
    }
  }

  function paintStatic() {
    if (!DATA) return;
    var sheetUrlAll = (DATA.sheet && DATA.sheet.url) || '#';
    ['#sheetLink', '#sheetFootLink'].forEach(function (sel) {
      var a = $(sel);
      if (a) a.href = sheetUrlAll;
    });
    var foot = $('#footMeta');
    if (foot) {
      foot.textContent = '데이터 기준 ' + (DATA.updated_label || '') +
        ' · 스캔 출처 ' + ((DATA.scan_basis && DATA.scan_basis.latest_scan) || '') +
        ' · 금액·마감·자격은 응찰 전 원문 재확인';
    }
    var stamp = $('#updatedAt');
    if (stamp) stamp.textContent = '업데이트 ' + (DATA.updated_label || '—');
  }

  function load(bust) {
    var url = DATA_URL + (bust ? '?t=' + Date.now() : '');
    fetch(url, { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (json) {
        DATA = json;
        buildItems();
        var box = $('#loadError');
        if (box) box.hidden = true;
        paintStatic();
        renderAll();
        updateToggles();
      })
      .catch(function (err) {
        showLoadError(err);
        var stamp = $('#updatedAt');
        if (stamp) stamp.textContent = '데이터 없음';
      });
  }

  function init() {
    bindEvents();
    readUrl();
    updateToggles();
    load(false);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
