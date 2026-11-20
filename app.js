/* =========================================================================
   나라장터 입찰 모니터링 대시보드
   - data.json 을 fetch 해서 렌더링 (단일 파일 빌드에서는 인라인 데이터)
   - 30일 창은 접속 시각 기준으로 매번 다시 계산
   ========================================================================== */
(function () {
  'use strict';

  var DATA_URL = 'data.json';
  var PAGE = 60;

  var DATA = null;
  var ITEMS = [];
  var NOW = new Date();
  var CUTOFF = new Date(NOW.getTime() - 30 * 86400000);

  var state = {
    tab: 'all',
    q: '',
    region: 'all',
    manager: 'all',
    keyword: 'all',
    sort: 'deadline',
    limit: PAGE
  };

  /* ---------------------------------------------------------------- utils */
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function won(n) {
    if (n == null || isNaN(n) || n === 0) return '—';
    n = Math.abs(Number(n));
    var eok = Math.floor(n / 1e8);
    var man = Math.floor((n % 1e8) / 1e4);
    var out = '';
    if (eok) out += eok.toLocaleString('ko-KR') + '억';
    if (man) out += (out ? ' ' : '') + man.toLocaleString('ko-KR') + '만';
    if (!out) out = n.toLocaleString('ko-KR');
    return out + '원';
  }
  function parseDate(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }
  function dday(iso) {
    var d = parseDate(iso);
    if (!d) return null;
    return Math.ceil((d.getTime() - NOW.getTime()) / 86400000);
  }
  function ddayClass(n) {
    if (n === null) return 'dday--past';
    if (n < 0) return 'dday--past';
    if (n <= 1) return 'dday--urgent';
    if (n <= 3) return 'dday--soon';
    if (n <= 7) return 'dday--ok';
    return '';
  }
  function ddayText(n) {
    if (n === null) return '—';
    if (n < 0) return '마감';
    if (n === 0) return 'D-DAY';
    return 'D-' + n;
  }
  function inWindow(it) {
    var p = parseDate(it.posted);
    if (!p) return true;
    return p.getTime() >= CUTOFF.getTime();
  }
  function statusBadge(it) {
    var s = it.status || '';
    var map = {
      '입찰중': ['badge--bid', '입찰중'],
      '개찰대기': ['badge--pending', '개찰대기'],
      '개찰완료': ['badge--opened', '개찰완료'],
      '유찰': ['badge--failed', '유찰'],
      '의견등록중': ['badge--pre', '의견등록중'],
      '의견마감': ['badge--wait', '의견마감']
    };
    var v = map[s] || ['badge--wait', s || '—'];
    return '<span class="badge ' + v[0] + '">' + esc(v[1]) + '</span>';
  }
  function kindBadge(it) {
    return it.kind === 'prespec'
      ? '<span class="badge badge--pre">사전규격</span>'
      : '<span class="badge badge--bid">입찰</span>';
  }
  function deadlineOf(it) { return it.deadline; }

  /* --------------------------------------------------------------- filter */
  function baseItems() {
    return ITEMS.filter(inWindow);
  }
  function filtered() {
    var q = state.q.trim().toLowerCase().replace(/\s+/g, '');
    var out = baseItems().filter(function (it) {
      if (state.tab === 'bid' && it.kind !== 'bid') return false;
      if (state.tab === 'prespec' && it.kind !== 'prespec') return false;
      if (state.tab === 'result') {
        if (it.kind !== 'bid') return false;
        if (!it.result || ['opened', 'failed', 'pending'].indexOf(it.result.state) < 0) return false;
      }
      if (state.region !== 'all' && it.region !== state.region) return false;
      if (state.manager !== 'all' && (it.managers || []).indexOf(state.manager) < 0) return false;
      if (state.keyword !== 'all' && (it.keywords || []).indexOf(state.keyword) < 0) return false;
      if (q) {
        var hay = (it.title + it.org + it.no + (it.region_detail || '') + (it.keywords || []).join('')).toLowerCase().replace(/\s+/g, '');
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
    out.sort(function (a, b) {
      if (state.sort === 'posted') {
        return (parseDate(b.posted) || 0) - (parseDate(a.posted) || 0);
      }
      if (state.sort === 'budget') {
        return (b.budget || 0) - (a.budget || 0);
      }
      if (state.tab === 'result') {
        var oa = parseDate(a.deadline), ob = parseDate(b.deadline);
        if (!oa && !ob) return 0;
        if (!oa) return 1;
        if (!ob) return -1;
        return ob - oa;
      }
      var da = parseDate(a.deadline), db = parseDate(b.deadline);
      if (!da && !db) return 0;
      if (!da) return 1;
      if (!db) return -1;
      var na = da - NOW, nb = db - NOW;
      // 마감 전 → 임박 순, 지난 건은 뒤로
      if (na >= 0 && nb < 0) return -1;
      if (na < 0 && nb >= 0) return 1;
      return na - nb;
    });
    return out;
  }

  /* ----------------------------------------------------------------- KPI */
  function renderKpis() {
    var base = baseItems();
    var bids = base.filter(function (i) { return i.kind === 'bid'; });
    var openBids = bids.filter(function (i) { return i.status === '입찰중'; });
    var urgent = openBids.filter(function (i) {
      var d = dday(deadlineOf(i));
      return d !== null && d >= 0 && d <= 3;
    });
    var prespec = base.filter(function (i) { return i.kind === 'prespec' && i.status === '의견등록중'; });
    var opened = bids.filter(function (i) { return i.result && i.result.state === 'opened'; });
    var failed = bids.filter(function (i) { return i.result && i.result.state === 'failed'; });

    var cards = [
      { label: '진행 중 입찰', value: openBids.length, sub: '전국 · 입찰공고 마감 전', cls: 'kpi--accent' },
      { label: '마감 임박 D-3', value: urgent.length, sub: '3일 안에 입찰 마감', cls: 'kpi--warn' },
      { label: '사전규격 의견등록중', value: prespec.length, sub: '의견등록 마감 전', cls: '' },
      { label: '개찰결과', value: opened.length + failed.length, sub: '개찰완료 ' + opened.length + ' · 유찰 ' + failed.length, cls: '' },
      { label: '최근 30일 수집', value: base.length, sub: '입찰 ' + bids.length + ' · 사전규격 ' + (base.length - bids.length), cls: '' }
    ];
    $('#kpis').innerHTML = cards.map(function (c) {
      return '<div class="kpi ' + c.cls + '">' +
        '<div class="kpi__label">' + c.label + '</div>' +
        '<div class="kpi__value">' + c.value + '<small>건</small></div>' +
        '<div class="kpi__sub">' + esc(c.sub) + '</div></div>';
    }).join('');

    var counts = { all: base.length, bid: bids.length, prespec: (base.length - bids.length), result: opened.length + failed.length + bids.filter(function (i) { return i.result && i.result.state === 'pending'; }).length };
    $$('[data-count]').forEach(function (el) {
      var k = el.getAttribute('data-count');
      el.textContent = counts[k] != null ? counts[k] : '';
    });
  }

  /* --------------------------------------------------------------- watch */
  function renderWatch() {
    var list = DATA.watchlist || [];
    if (!list.length) { $('#watch').hidden = true; return; }
    $('#watch').innerHTML = list.map(function (w) {
      var cls = w.tone === 'urgent' ? ' watch__card--urgent' : '';
      return '<div class="watch__card' + cls + '">' +
        '<div class="watch__body">' +
        '<div class="watch__title">' + esc(w.label) + ' <span class="badge ' + (w.tone === 'urgent' ? 'badge--pending' : 'badge--wait') + '">' + esc(w.status) + '</span></div>' +
        '<div class="watch__meta">' + esc(w.meta || '') + '</div>' +
        '<div class="watch__note">' + esc(w.note || '') + '</div>' +
        '</div>' +
        (w.g2b ? '<a class="btn" href="' + esc(w.g2b) + '" target="_blank" rel="noopener">나라장터</a>' : '') +
        '</div>';
    }).join('');
  }

  /* ------------------------------------------------------------ managers */
  function renderManagers() {
    var base = baseItems();
    var mgrs = DATA.managers || [];
    var regions = {};
    base.forEach(function (i) { regions[i.region] = (regions[i.region] || 0) + 1; });

    $('#managerGrid').innerHTML = mgrs.map(function (m) {
      var mine = base.filter(function (i) { return (i.managers || []).indexOf(m.name) >= 0; });
      var openBids = mine.filter(function (i) { return i.kind === 'bid' && i.status === '입찰중'; });
      var ps = mine.filter(function (i) { return i.kind === 'prespec' && i.status === '의견등록중'; });
      var urgent = openBids.filter(function (i) { var d = dday(deadlineOf(i)); return d !== null && d >= 0 && d <= 3; });
      var sum = openBids.reduce(function (a, i) { return a + (i.budget || 0); }, 0);
      var byRegion = {};
      mine.forEach(function (i) { byRegion[i.region] = (byRegion[i.region] || 0) + 1; });
      var total = mine.length || 1;
      var bar = Object.keys(byRegion).sort(function (a, b) { return byRegion[b] - byRegion[a]; }).slice(0, 6).map(function (r, idx) {
        var colors = ['#2563eb', '#7c3aed', '#059669', '#d97706', '#0ea5e9', '#dc2626'];
        return '<i style="width:' + (byRegion[r] / total * 100) + '%;background:' + colors[idx % 6] + '" title="' + esc(r) + ' ' + byRegion[r] + '건"></i>';
      }).join('');

      return '<article class="mgr" data-mgr="' + esc(m.name) + '" tabindex="0" role="button">' +
        '<div class="mgr__top">' +
        '<span class="mgr__dot" style="background:' + m.color + '"></span>' +
        '<span class="mgr__name">' + esc(m.name) + '</span>' +
        '<span class="mgr__regions">' + esc(m.regions.join(' · ')) + '</span>' +
        '</div>' +
        '<div class="mgr__stats">' +
        '<div class="mgr__stat"><b>' + openBids.length + '</b><span>진행 중 입찰</span></div>' +
        '<div class="mgr__stat"><b>' + ps.length + '</b><span>사전규격</span></div>' +
        '<div class="mgr__stat"><b>' + urgent.length + '</b><span>마감 임박 D-3</span></div>' +
        '<div class="mgr__stat"><b>' + (sum ? (Math.round(sum / 1e8 * 10) / 10) + '억' : '—') + '</b><span>예산 합계</span></div>' +
        '</div>' +
        '<div class="mgr__foot"><span>권역 ' + mine.length + '건</span><span class="mgr__bar">' + bar + '</span><span>' + (m.regions.indexOf('경기') >= 0 ? '경기 중복' : '') + '</span></div>' +
        '</article>';
    }).join('');

    var chips = Object.keys(regions).sort(function (a, b) { return regions[b] - regions[a]; }).map(function (r) {
      return '<button class="chip' + (state.region === r ? ' is-active' : '') + '" data-region="' + esc(r) + '">' + esc(r) + '<span class="chip__n">' + regions[r] + '</span></button>';
    }).join('');
    $('#regionStrip').innerHTML = '<button class="chip' + (state.region === 'all' ? ' is-active' : '') + '" data-region="all">전체 지역</button>' + chips;
  }

  /* -------------------------------------------------------------- filters */
  function renderFilters() {
    var base = baseItems();
    var regions = {};
    base.forEach(function (i) { regions[i.region] = (regions[i.region] || 0) + 1; });
    var opts = ['<option value="all">전체 지역</option>'].concat(Object.keys(regions).sort(function (a, b) {
      return regions[b] - regions[a];
    }).map(function (r) {
      return '<option value="' + esc(r) + '"' + (state.region === r ? ' selected' : '') + '>' + esc(r) + ' (' + regions[r] + ')</option>';
    }));
    var sel = $('#regionSel');
    sel.innerHTML = opts.join('');

    var mgrNames = (DATA.managers || []).map(function (m) { return m.name; });
    $('#managerChips').innerHTML = '<button class="chip chip--mgr' + (state.manager === 'all' ? ' is-active' : '') + '" data-mgr="all">담당자 전체</button>' +
      mgrNames.map(function (n) {
        var c = base.filter(function (i) { return (i.managers || []).indexOf(n) >= 0; }).length;
        return '<button class="chip chip--mgr' + (state.manager === n ? ' is-active' : '') + '" data-mgr="' + esc(n) + '">' + esc(n) + '<span class="chip__n">' + c + '</span></button>';
      }).join('');

    var stats = (DATA.keyword_stats || []).filter(function (k) { return k.bids + k.prespec > 0; });
    $('#keywordChips').innerHTML = '<button class="chip' + (state.keyword === 'all' ? ' is-active' : '') + '" data-kw="all">키워드 전체</button>' +
      stats.map(function (k) {
        return '<button class="chip' + (state.keyword === k.keyword ? ' is-active' : '') + '" data-kw="' + esc(k.keyword) + '">' + esc(k.keyword) +
          '<span class="chip__n">' + (k.bids + k.prespec) + '</span></button>';
      }).join('');
  }

  /* ----------------------------------------------------------------- list */
  function rowHtml(it) {
    var d = dday(deadlineOf(it));
    var tags = (it.keywords || []).slice(0, 3).map(function (k) { return '<span class="tag tag--kw">' + esc(k) + '</span>'; }).join('');
    var mgrs = (it.managers || []).map(function (m) { return '<span class="tag tag--mgr">' + esc(m) + '</span>'; }).join('');
    var att = it.attachments && it.attachments.length ? '<span class="tag tag--she">첨부 ' + it.attachments.length + '</span>' : '';
    return '<article class="row" data-id="' + esc(it.id) + '" tabindex="0" role="button">' +
      '<div class="dday ' + ddayClass(d) + '">' + ddayText(d) + '<small>' + esc(it.deadline_short || '') + '</small></div>' +
      '<div class="row__main">' +
      '<div class="row__title">' + esc(it.title) + '</div>' +
      '<div class="row__meta"><span>' + esc(it.org) + '</span><span class="dot">·</span><span>' + esc(it.region_detail || it.region) + '</span><span class="dot">·</span><span>' + esc(it.no) + '</span></div>' +
      '<div class="row__tags">' + tags + mgrs + att + '</div>' +
      '</div>' +
      '<div class="row__money"><b>' + esc(it.budget ? won(it.budget) : (it.budget_text || '—')) + '</b><small>' + esc(it.contract || it.biz || '') + '</small></div>' +
      '<div class="row__when"><b>' + esc(it.deadline_short || '일정 확인') + '</b><small>' + esc(it.deadline_kind) + '</small></div>' +
      '<div class="row__state">' + kindBadge(it) + ' ' + statusBadge(it) + '</div>' +
      '</article>';
  }

  function resultRow(it) {
    var r = it.result || {};
    var label = r.state === 'opened' ? '개찰완료' : (r.state === 'failed' ? '유찰' : '개찰대기');
    var cls = r.state === 'opened' ? 'badge--opened' : (r.state === 'failed' ? 'badge--failed' : 'badge--pending');
    var winner = r.winner || (r.state === 'failed' ? '유찰 (참가 ' + (r.participants == null ? '?' : r.participants) + ')' : '결과 미게시');
    return '<article class="res" data-id="' + esc(it.id) + '" tabindex="0" role="button">' +
      '<div class="res__main">' +
      '<div class="row__title">' + esc(it.title) + '</div>' +
      '<div class="row__meta"><span>' + esc(it.org) + '</span><span class="dot">·</span><span>' + esc(it.region) + '</span><span class="dot">·</span><span>' + esc(it.no) + '</span>' +
      '<span class="badge ' + cls + '" style="margin-left:4px">' + label + '</span></div>' +
      '</div>' +
      '<div class="res__num"><b>' + (r.participants == null ? '—' : r.participants) + '</b><small>참가업체</small></div>' +
      '<div class="res__win"><b>' + esc(winner) + '</b><small>' + esc(r.amount ? won(r.amount) + (r.rate ? ' · 낙찰률 ' + r.rate + '%' : '') : (r.note || '')) + '</small></div>' +
      '<div class="row__when"><b>' + esc(it.deadline_short || '—') + '</b><small>개찰 ' + esc(it.open_label || '—') + '</small></div>' +
      '</article>';
  }

  function renderList() {
    var rows = filtered();
    var titleMap = { all: '전체', bid: '입찰공고', prespec: '사전규격', result: '개찰결과' };
    $('#listTitle').textContent = titleMap[state.tab] || '전체';
    var bits = [];
    if (state.manager !== 'all') bits.push('담당 ' + state.manager);
    if (state.region !== 'all') bits.push(state.region);
    if (state.keyword !== 'all') bits.push('키워드 ' + state.keyword);
    $('#listMeta').textContent = rows.length + '건' + (bits.length ? ' · ' + bits.join(' · ') : '');

    var shown = rows.slice(0, state.limit);
    var html = state.tab === 'result' ? shown.map(resultRow).join('') : shown.map(rowHtml).join('');
    $('#list').innerHTML = html;

    if (!rows.length) {
      $('#emptyState').hidden = false;
      $('#emptyState').textContent = '조건에 맞는 건이 없습니다. 필터를 풀거나 data.json 기준일(' + (DATA.updated_label || '') + ')을 확인하세요.';
    } else {
      $('#emptyState').hidden = true;
    }
    var more = $('#list').nextElementSibling;
    if (rows.length > shown.length) {
      if (!more || !more.classList.contains('more')) {
        var div = document.createElement('div');
        div.className = 'more';
        div.innerHTML = '<button class="btn" id="moreBtn">더 보기 (' + (rows.length - shown.length) + '건)</button>';
        $('#list').after(div);
      } else {
        more.innerHTML = '<button class="btn" id="moreBtn">더 보기 (' + (rows.length - shown.length) + '건)</button>';
      }
    } else if (more && more.classList.contains('more')) {
      more.remove();
    }
  }

  /* --------------------------------------------------------------- drawer */
  function fileExt(name) {
    var m = /\.([a-z0-9]+)$/i.exec(name || '');
    return m ? m[1].toUpperCase().slice(0, 4) : 'FILE';
  }

  function openDrawer(id) {
    var it = ITEMS.filter(function (i) { return i.id === id; })[0];
    if (!it) return;
    var d = dday(deadlineOf(it));
    var r = it.result || {};

    var files = (it.attachments || []).length
      ? it.attachments.map(function (f) {
        return '<a class="file" href="' + esc(f.url) + '" target="_blank" rel="noopener">' +
          '<span class="file__ext">' + esc(fileExt(f.name)) + '</span>' +
          '<span class="file__name">' + esc(f.name) + '</span>' +
          '<span class="file__dl">열기</span></a>';
      }).join('')
      : '<div class="qa">' + (it.kind === 'prespec'
        ? '사전규격은 나라장터 사전규격 상세(로그인)에서 첨부 규격서를 확인해야 합니다. 공개 수집원에는 첨부 목록이 없습니다.'
        : '첨부파일 목록을 확인하지 못했습니다. 나라장터 원문에서 확인하세요.') + '</div>';

    var qnaState = { confirmed: '확인', noted: '일부 확인', none: '등록된 질의 없음', unknown: '미확인' }[it.qna.state] || '미확인';
    var qnaCls = it.qna.state === 'none' ? 'badge--wait' : (it.qna.state === 'unknown' ? 'badge--unknown' : 'badge--pre');
    var qnaItems = (it.qna.items || []).map(function (q) {
      return '<div class="qa__item"><b>Q. ' + esc(q.q) + '</b><br>A. ' + esc(q.a) + '</div>';
    }).join('');

    var resultHtml;
    if (it.kind === 'prespec') {
      resultHtml = '<div class="qa">사전규격 단계입니다. 본공고 전환 후 개찰결과가 표시됩니다.</div>';
    } else if (r.state === 'opened') {
      resultHtml = '<div class="result-box"><div class="result-box__head"><span class="badge badge--opened">개찰완료</span>' +
        (r.opened_at ? '<span class="muted small">개찰 ' + esc(r.opened_at.slice(0, 16).replace('T', ' ')) + '</span>' : '') + '</div>' +
        '<div class="result-box__body"><div class="result-grid">' +
        '<div class="result-cell"><span>참가업체</span><b>' + (r.participants == null ? '미확인' : r.participants + '곳') + '</b></div>' +
        '<div class="result-cell"><span>낙찰·계약업체</span><b>' + esc(r.winner || '미확인') + '</b></div>' +
        '<div class="result-cell"><span>낙찰·계약금액</span><b>' + (r.amount ? won(r.amount) : '미확인') + '</b></div>' +
        '<div class="result-cell"><span>낙찰률</span><b>' + (r.rate ? r.rate + '%' : '미공개') + '</b></div>' +
        '</div>' + (r.note ? '<p class="small muted" style="margin:10px 0 0">' + esc(r.note) + '</p>' : '') +
        '<p class="small muted" style="margin:8px 0 0">참가업체 수·낙찰 정보는 수집원(presignal·공공일감) 표기값입니다.</p>' +
        '</div></div>';
    } else if (r.state === 'failed') {
      resultHtml = '<div class="result-box"><div class="result-box__head"><span class="badge badge--failed">유찰</span>' +
        '<span class="muted small">' + (r.participants != null ? '참가 ' + r.participants + '곳' : '참가 정보 없음') + '</span></div></div>';
    } else if (r.state === 'pending') {
      resultHtml = '<div class="result-box"><div class="result-box__head"><span class="badge badge--pending">개찰결과 대기</span></div>' +
        '<div class="result-box__body small muted">마감은 지났지만 개찰결과가 아직 게시되지 않았습니다. (' + esc(r.note || '') + ')</div></div>';
    } else {
      resultHtml = '<div class="qa">마감 전입니다. 개찰결과는 개찰 후 표시됩니다.</div>';
    }

    var copyTarget = it.kind === 'prespec' ? it.no : it.no + '-' + (it.order || '000');

    $('#drawer').innerHTML =
      '<div class="dw-head">' +
      '<div class="dw-head__top">' + kindBadge(it) + statusBadge(it) +
      '<span class="dday ' + ddayClass(d) + '" style="margin-left:6px;padding:3px 8px">' + ddayText(d) + '</span>' +
      '<button class="dw-close" data-close="1" aria-label="닫기">✕</button></div>' +
      '<div class="dw-title">' + esc(it.title) + '</div>' +
      '<div class="dw-sub"><span>' + esc(it.org) + '</span><span>·</span><span>' + esc(it.no) + '</span><span>·</span><span>' + esc(it.region_detail || it.region) + '</span></div>' +
      '</div>' +
      '<div class="dw-body">' +
      (it.note ? '<div class="dw-sec"><div class="note">' + esc(it.note) + '</div></div>' : '') +
      '<div class="dw-sec"><h3>핵심 정보</h3><dl class="kv">' +
      '<dt>추정가격</dt><dd>' + esc(it.price_est ? won(it.price_est) : '—') + '</dd>' +
      '<dt>배정예산</dt><dd>' + esc(it.budget ? won(it.budget) : (it.budget_text || '—')) + '</dd>' +
      '<dt>' + esc(it.deadline_kind) + '</dt><dd>' + esc(it.deadline_label || '공고문 확인') + (it.deadline_note ? ' <span class="small muted">(' + esc(it.deadline_note) + ')</span>' : '') + '</dd>' +
      '<dt>개찰</dt><dd>' + esc(it.open_label || '공고문 확인') + '</dd>' +
      '<dt>계약방법</dt><dd>' + esc(it.contract || '—') + '</dd>' +
      '<dt>지역제한</dt><dd>' + esc(it.region_limit || '공고문 확인') + '</dd>' +
      '<dt>업종제한</dt><dd>' + esc(it.industry_limit || '공고문 확인') + '</dd>' +
      '<dt>참가조건</dt><dd>' + esc(it.conditions || '공고문 확인') + '</dd>' +
      '<dt>담당권역</dt><dd>' + esc((it.managers || []).length ? it.managers.join(' · ') : '권역 외(전국·타 지역)') + '</dd>' +
      '<dt>키워드</dt><dd>' + esc((it.keywords || []).join(' · ')) + '</dd>' +
      '</dl></div>' +
      '<div class="dw-sec"><h3>첨부파일 <span class="badge badge--pre">' + ((it.attachments || []).length || '미확인') + '</span></h3><div class="files">' + files + '</div></div>' +
      '<div class="dw-sec"><h3>사전규격 질의 <span class="badge ' + qnaCls + '">' + qnaState + '</span></h3>' +
      '<div class="qa">' + esc(it.qna.summary || '') + qnaItems + '</div></div>' +
      '<div class="dw-sec"><h3>개찰결과</h3>' + resultHtml + '</div>' +
      '<div class="dw-sec"><h3>원문 · 링크</h3><div class="actions">' +
      '<a class="btn btn--primary" href="' + esc(it.links.g2b) + '" target="_blank" rel="noopener">나라장터 ' + (it.kind === 'prespec' ? '열기' : '공고 상세') + '</a>' +
      '<button class="btn" type="button" data-copy="' + esc(copyTarget) + '">공고번호 복사</button>' +
      '<a class="btn" href="' + esc(it.links.presignal) + '" target="_blank" rel="noopener">수집원 상세</a>' +
      (it.links.data00 ? '<a class="btn" href="' + esc(it.links.data00) + '" target="_blank" rel="noopener">공공일감</a>' : '') +
      '<span class="copy-hint" id="copyHint">복사됨</span>' +
      '</div><p class="small muted" style="margin:8px 0 0">' +
      (it.kind === 'prespec'
        ? '사전규격(R26BD…)은 나라장터에서 공고번호로 바로 열리는 딥링크가 없습니다. 번호를 복사해 나라장터 사전규격 화면에서 검색하세요.'
        : '나라장터 입찰공고 상세로 바로 열립니다.') + '</p></div>' +
      '</div>';

    $('#drawerWrap').hidden = false;
    document.body.style.overflow = 'hidden';
    $('#drawer').scrollTop = 0;
  }

  function closeDrawer() {
    $('#drawerWrap').hidden = true;
    document.body.style.overflow = '';
  }

  /* -------------------------------------------------------------- footer */
  function renderFooter() {
    var w = DATA.window || {};
    var c = DATA.counts || {};
    $('#foot').innerHTML =
      '<div><b>데이터 기준</b> ' + esc(DATA.updated_label || '') + ' · 조회 구간 ' + esc(w.from || '') + ' ~ ' + esc(w.to || '') + ' (최근 ' + (w.days || 30) + '일, 공고일 기준)</div>' +
      '<div><b>수집 현황</b> 입찰공고 ' + (c.bids || 0) + '건 · 사전규격 ' + (c.prespec || 0) + '건 · 첨부 확인 ' + (c.attachments || 0) + '건 · 개찰완료 ' + (c.opened || 0) + '건 · 유찰 ' + (c.failed || 0) + '건</div>' +
      '<div><b>출처</b> ' + esc((DATA.scan_basis && DATA.scan_basis.sources) || '') + '</div>' +
      '<div><b>주의</b> 금액·마감·자격은 수집 시점 정리값입니다. 응찰 판단 전 나라장터 공고문·제안요청서 원문으로 재확인하십시오. 화면의 D-day는 접속한 날짜 기준으로 자동 계산되며, 30일이 지난 공고는 자동으로 빠집니다.</div>';
  }

  /* --------------------------------------------------------------- events */
  function setTab(tab) {
    state.tab = tab;
    state.limit = PAGE;
    $$('.tab').forEach(function (b) { b.classList.toggle('is-active', b.getAttribute('data-tab') === tab); });
    var isMgr = tab === 'managers';
    $('#managerView').hidden = !isMgr;
    $('#listView').hidden = isMgr;
    if (isMgr) {
      renderManagers();
    } else {
      renderFilters();
      renderList();
    }
  }

  function bind() {
    $('#tabs').addEventListener('click', function (e) {
      var b = e.target.closest('.tab');
      if (b) setTab(b.getAttribute('data-tab'));
    });
    $('#q').addEventListener('input', function (e) {
      state.q = e.target.value; state.limit = PAGE; renderList();
    });
    $('#regionSel').addEventListener('change', function (e) {
      state.region = e.target.value; state.limit = PAGE; renderList();
    });
    $('#sortSel').addEventListener('change', function (e) {
      state.sort = e.target.value; state.limit = PAGE; renderList();
    });
    $('#managerChips').addEventListener('click', function (e) {
      var b = e.target.closest('[data-mgr]');
      if (!b) return;
      state.manager = b.getAttribute('data-mgr'); state.limit = PAGE; renderFilters(); renderList();
    });
    $('#keywordChips').addEventListener('click', function (e) {
      var b = e.target.closest('[data-kw]');
      if (!b) return;
      state.keyword = b.getAttribute('data-kw'); state.limit = PAGE; renderFilters(); renderList();
    });
    $('#regionStrip').addEventListener('click', function (e) {
      var b = e.target.closest('[data-region]');
      if (!b) return;
      state.region = b.getAttribute('data-region');
      setTab('all');
    });
    $('#managerGrid').addEventListener('click', function (e) {
      var card = e.target.closest('[data-mgr]');
      if (!card) return;
      state.manager = card.getAttribute('data-mgr');
      setTab('all');
    });
    $('#managerGrid').addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var card = e.target.closest('[data-mgr]');
      if (!card) return;
      e.preventDefault();
      state.manager = card.getAttribute('data-mgr');
      setTab('all');
    });
    $('#list').addEventListener('click', function (e) {
      var row = e.target.closest('[data-id]');
      if (row) openDrawer(row.getAttribute('data-id'));
    });
    $('#list').addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var row = e.target.closest('[data-id]');
      if (!row) return;
      e.preventDefault();
      openDrawer(row.getAttribute('data-id'));
    });
    document.addEventListener('click', function (e) {
      var more = e.target.closest('#moreBtn');
      if (more) { state.limit += PAGE; renderList(); return; }
      if (e.target.closest('[data-close]')) { closeDrawer(); return; }
      var cp = e.target.closest('[data-copy]');
      if (cp) copyText(cp.getAttribute('data-copy'));
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !$('#drawerWrap').hidden) closeDrawer();
    });
    $('#reloadBtn').addEventListener('click', function () { location.reload(true); });
  }

  function copyText(text) {
    var done = function () {
      var h = $('#copyHint');
      if (h) { h.classList.add('show'); setTimeout(function () { h.classList.remove('show'); }, 1600); }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); } catch (err) { alert('복사 실패: ' + text); }
      document.body.removeChild(ta);
    }
  }

  /* ----------------------------------------------------------------- boot */
  function boot(data) {
    DATA = data;
    ITEMS = (data.items || []).slice();
    $('#updatedStamp').textContent = (data.updated_label || '') + ' 기준 · 30일';
    renderKpis();
    renderWatch();
    renderFilters();
    renderList();
    renderFooter();
    bind();
  }

  function fail(msg) {
    var el = $('#loadError');
    el.hidden = false;
    el.innerHTML = msg;
  }

  fetch(DATA_URL, { cache: 'no-store' })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(boot)
    .catch(function (err) {
      fail('데이터를 불러오지 못했습니다 (' + esc(err.message) + '). <br>' +
        'index.html을 파일로 직접 열었다면 로컬 서버로 열어 주세요: <code>python3 -m http.server 8000</code>');
    });
})();
