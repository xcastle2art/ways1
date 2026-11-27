/* =========================================================================
   나라장터 입찰 모니터링 — 시·도별 대시보드 (data.json 기반, 빌드 없음)
   화면 순서: 시·도 내비 → 지금 챙길 것(D-3 이내) → 종류/검색 → 목록 → 추적 → 출처
   ========================================================================== */
(function () {
  'use strict';

  var DATA_URL = 'data.json';
  var PAGE = 80;
  var NOW = new Date();
  /* 30일 창은 날짜 기준(자정)으로 계산해 data.json 구간과 어긋나지 않게 */
  var CUTOFF = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate() - 30);

  var DATA = null;
  var ITEMS = [];
  var state = { sido: 'all', kind: 'all', q: '', kw: 'all', sort: 'deadline', limit: PAGE, urgentOnly: false, includePast: true };

  /* ------------------------------------------------------------- helpers */
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function parseDate(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }
  /* 달력 기준 D-day (자정 넘어가면 하루 줄어듦) */
  function ddayOf(iso) {
    var d = parseDate(iso);
    if (!d) return null;
    var a = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
    var b = Date.UTC(NOW.getFullYear(), NOW.getMonth(), NOW.getDate());
    return Math.round((a - b) / 86400000);
  }
  function ddayText(n) {
    if (n === null) return '—';
    if (n < 0) return '마감';
    if (n === 0) return 'D-DAY';
    return 'D-' + n;
  }
  function ddayCls(n) {
    if (n === null || n < 0) return 'dd--past';
    if (n <= 1) return 'dd--u1';
    if (n <= 3) return 'dd--u3';
    return 'dd--ok';
  }
  /* 금액: 4.4억 / 8,949만 */
  function wonShort(n) {
    n = Number(n);
    if (!n || isNaN(n)) return '';
    if (n >= 1e8) {
      var eok = Math.round(n / 1e7) / 10;
      return (eok % 1 === 0 ? eok.toFixed(0) : eok.toFixed(1)) + '억';
    }
    return Math.round(n / 1e4).toLocaleString('ko-KR') + '만';
  }
  function isoShort(iso) {
    var d = parseDate(iso);
    if (!d) return '';
    return pad(d.getMonth() + 1) + '.' + pad(d.getDate());
  }
  /* 행 왼쪽 칸용 짧은 마감 표기: 11.24 10:00 */
  function dlShort(it) {
    var d = parseDate(it.deadline);
    if (!d) return '일정 확인';
    return pad(d.getMonth() + 1) + '.' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }
  function inWindow(it) {
    var p = parseDate(it.posted);
    return !p || p.getTime() >= CUTOFF.getTime();
  }
  function baseItems() { return ITEMS.filter(inWindow); }
  function isOpen(it) { return it.status === '입찰중' || it.status === '의견등록중'; }
  function isUrgent(it) {
    var n = ddayOf(it.deadline);
    return n !== null && n >= 0 && n <= 3 && isOpen(it);
  }
  function amountOf(it) {
    if (it.budget) return { label: '배정', text: wonShort(it.budget), raw: it.budget };
    if (it.price_est) return { label: '추정', text: wonShort(it.price_est), raw: it.price_est };
    if (it.budget_text) return { label: '', text: String(it.budget_text).replace(/\s*원$/, ''), raw: 0 };
    return { label: '', text: '', raw: 0 };
  }
  function pillOf(it) {
    var s = it.status || '';
    var map = {
      '입찰중': 'pill--bid', '개찰대기': 'pill--pending', '개찰완료': 'pill--opened',
      '유찰': 'pill--failed', '재입찰': 'pill--pending', '의견등록중': 'pill--pre', '의견마감': 'pill--wait'
    };
    return '<span class="pill ' + (map[s] || 'pill--wait') + '">' + esc(s || '—') + '</span>';
  }
  function kindPill(it) {
    return it.kind === 'prespec'
      ? '<span class="pill pill--pre">사전규격</span>'
      : '<span class="pill pill--bid">입찰공고</span>';
  }
  /* ------------------------------------------------- 입찰가능 여부(업체 매칭) */
  var VERDICT = {
    '가능': { cls: 'ok', mark: '✓', label: '참가가능' },
    '조건부': { cls: 'cond', mark: '△', label: '조건부' },
    '불가': { cls: 'no', mark: '✕', label: '불가' },
    '요건미확인': { cls: 'unk', mark: '?', label: '요건 미확인' }
  };
  function V(v) { return VERDICT[v] || VERDICT['요건미확인']; }
  function eligChip(it) {
    var e = it && it.elig;
    if (!e) return '';
    var v = V(e.verdict);
    var tip = (e.reasons || []).join(' / ');
    return '<span class="echip echip--' + v.cls + '"' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' +
      v.mark + ' 웨이즈원 ' + v.label + '</span>';
  }
  function indShort(s) {
    return String(s || '')
      .replace('엔지니어링·', '엔지·')
      .replace('SW사업자 신고', 'SW사업자')
      .replace('측량업·', '');
  }

  function regionLimited(it) {
    var v = it.region_limit || '';
    return v && v.indexOf('없음') < 0 ? v : '';
  }
  /* 발주기관 앞의 시·도 이름은 목록에서 빼고 읽기 쉽게 (예: 경기도 화성시 → 화성시) */
  var SIDO_PREFIX = /^(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원특별자치도|강원도|충청북도|충청남도|전라북도|전북특별자치도|전라남도|경상북도|경상남도|제주특별자치도)\s*/;
  function shortOrg(org) {
    var s = String(org || '');
    if (!SIDO_PREFIX.test(s)) return s;
    var t = s.replace(SIDO_PREFIX, '');
    // 시·군·구 이름으로 시작할 때만 줄인다 (예: '대전광역시교육청' → 그대로)
    return /^[가-힣]{1,4}(시|군|구)(\s|$)/.test(t) ? t : s;
  }

  /* ------------------------------------------------------------- 내비게이션 */
  function renderSido() {
    var base = baseItems();
    var counts = {};
    base.forEach(function (i) { counts[i.region] = (counts[i.region] || 0) + 1; });
    var total = base.length;
    var html = '<button class="sido__btn' + (state.sido === 'all' ? ' is-active' : '') + '" data-sido="all" type="button">전체<span class="sido__n">' + total + '</span></button>';
    (DATA.provinces || []).forEach(function (p) {
      var n = counts[p.code] || 0;
      html += '<button class="sido__btn' + (state.sido === p.code ? ' is-active' : '') + (n ? '' : ' is-zero') +
        '" data-sido="' + esc(p.code) + '" type="button"' + (n ? '' : ' aria-disabled="true"') + '>' +
        esc(p.name) + '<span class="sido__n">' + n + '</span></button>';
    });
    $('#sidoNav').innerHTML = html;
  }

  function scoped() {
    var base = baseItems();
    return state.sido === 'all' ? base : base.filter(function (i) { return i.region === state.sido; });
  }

  /* -------------------------------------------------- 지금 챙길 것 (긴급) */
  function renderUrgent() {
    var box = $('#urgent');
    var all = baseItems().filter(isUrgent).sort(function (a, b) {
      return new Date(a.deadline) - new Date(b.deadline);
    });
    var shown = all.slice(0, window.innerWidth <= 760 ? 5 : 7);
    var head = '<div class="urgent__head"><span class="urgent__title"><i></i>지금 챙길 것</span>' +
      '<span class="urgent__sub">D-3 이내 마감 ' + all.length + '건</span>' +
      (all.length > shown.length ? '<button class="linkbtn" id="urgentAll" type="button">' + all.length + '건 전체 보기</button>' : '') +
      '</div>';

    if (!all.length) {
      box.innerHTML = head + '<div class="urgent__empty"><b>3일 안에 마감되는 건이 없습니다.</b> 목록에서 여유 있는 건을 확인하세요.</div>';
      box.hidden = false;
      return;
    }
    var rows = shown.map(function (it) {
      var n = ddayOf(it.deadline);
      return '<button class="urg" type="button" data-id="' + esc(it.id) + '">' +
        '<span class="dd ' + ddayCls(n) + '">' + ddayText(n) + '</span>' +
        '<span class="urg__k' + (it.kind === 'prespec' ? ' urg__k--pre' : '') + '">' + (it.kind === 'prespec' ? '의견' : '입찰') + '</span>' +
        '<span class="urg__t">' + esc(it.title) + '</span>' +
        '<span class="urg__w">' + esc(it.deadline_short || '') + '</span>' +
        '</button>';
    }).join('');
    box.innerHTML = head + '<div class="urgent__grid">' + rows + '</div>';
    box.hidden = false;
  }

  /* -------------------------------------------------------------- 툴바 */
  function renderKind() {
    var sub = scoped();
    var bids = sub.filter(function (i) { return i.kind === 'bid'; });
    var res = bids.filter(function (i) { return i.result && ['opened', 'failed', 'pending'].indexOf(i.result.state) >= 0; });
    var c = { all: sub.length, bid: bids.length, prespec: sub.length - bids.length, result: res.length };
    var defs = [['all', '전체'], ['bid', '입찰공고'], ['prespec', '사전규격'], ['result', '개찰결과']];
    $('#kindSeg').innerHTML = defs.map(function (d) {
      return '<button type="button" role="tab" data-kind="' + d[0] + '" class="' + (state.kind === d[0] ? 'is-active' : '') +
        '" aria-selected="' + (state.kind === d[0]) + '">' + d[1] + '<b>' + c[d[0]] + '</b></button>';
    }).join('');

    var kws = {};
    sub.forEach(function (i) {
      (i.keywords || []).forEach(function (k) { kws[k] = (kws[k] || 0) + 1; });
    });
    var list = (DATA.dashboard_keywords || Object.keys(kws)).filter(function (k) { return kws[k]; });
    list.sort(function (a, b) { return kws[b] - kws[a]; });
    $('#kwRow').innerHTML = '<span class="kwrow__label">키워드</span>' +
      '<button class="kw' + (state.kw === 'all' ? ' is-active' : '') + '" data-kw="all" type="button">전체</button>' +
      list.map(function (k) {
        return '<button class="kw' + (state.kw === k ? ' is-active' : '') + '" data-kw="' + esc(k) + '" type="button">' +
          esc(k) + '<span class="kw__n">' + kws[k] + '</span></button>';
      }).join('');
  }

  /* -------------------------------------------------------------- 목록 */
  function filtered() {
    var q = state.q.trim().toLowerCase().replace(/\s+/g, '');
    var out = scoped().filter(function (it) {
      if (state.urgentOnly && !isUrgent(it)) return false;
      if (!state.includePast && state.kind !== 'result') {
        var dd = ddayOf(it.deadline);
        if (dd !== null && dd < 0) return false;
      }
      if (state.kind === 'bid' && it.kind !== 'bid') return false;
      if (state.kind === 'prespec' && it.kind !== 'prespec') return false;
      if (state.kind === 'result') {
        if (it.kind !== 'bid' || !it.result || ['opened', 'failed', 'pending'].indexOf(it.result.state) < 0) return false;
      }
      if (state.kw !== 'all' && (it.keywords || []).indexOf(state.kw) < 0) return false;
      if (q) {
        var hay = (it.title + it.org + it.no + (it.region_detail || '') + (it.keywords || []).join('')).toLowerCase().replace(/\s+/g, '');
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
    out.sort(function (a, b) {
      if (state.sort === 'posted') return (parseDate(b.posted) || 0) - (parseDate(a.posted) || 0);
      if (state.sort === 'budget') return (b.budget || b.price_est || 0) - (a.budget || a.price_est || 0);
      if (state.kind === 'result') {
        var oa = parseDate(a.deadline), ob = parseDate(b.deadline);
        return (ob || 0) - (oa || 0);
      }
      var da = parseDate(a.deadline), db = parseDate(b.deadline);
      if (!da && !db) return 0;
      if (!da) return 1;
      if (!db) return -1;
      var na = da - NOW, nb = db - NOW;
      if (na >= 0 && nb < 0) return -1;   // 마감 전 → 임박 순, 지난 건은 뒤로
      if (na < 0 && nb >= 0) return 1;
      return na - nb;
    });
    return out;
  }

  function rowHtml(it) {
    var n = ddayOf(it.deadline);
    var amt = amountOf(it);
    var cls = 'row';
    if (n !== null && n < 0) cls += ' is-past';
    if (it.status === '개찰완료') cls += ' row--done';
    else if (it.status === '유찰' || it.status === '재입찰') cls += ' row--fail';
    else if (n !== null && n >= 0 && n <= 1) cls += ' row--urgent';
    else if (n !== null && n >= 0 && n <= 3) cls += ' row--soon';
    else cls += ' row--open';

    var meta = eligChip(it) +
      (it.elig && it.elig.eligible_count ? '<span class="row__elig-n">낙찰사 ' + it.elig.eligible_count + '곳 입찰가능</span>' : '') +
      (it.elig && it.elig.complement_count ? '<span class="sep">·</span><span class="row__elig-n">보완 ' + it.elig.complement_count + '</span>' : '') +
      '<span class="sep">·</span><span class="row__org">' + esc(shortOrg(it.org)) + '</span>' +
      '<span class="sep">·</span><span>' + esc(it.no) + '</span>' +
      (it.kind === 'prespec' ? '<span class="sep">·</span><span>사전규격</span>' : '') +
      (regionLimited(it) ? '<span class="sep">·</span><span class="row__flag">지역제한</span>' : '') +
      (it.attachments && it.attachments.length ? '<span class="sep">·</span><span>첨부 ' + it.attachments.length + '</span>' : '');

    var badge = pillOf(it);

    return '<article class="' + cls + '" data-id="' + esc(it.id) + '" tabindex="0" role="button">' +
      '<div class="row__d"><span class="dd ' + ddayCls(n) + '">' + ddayText(n) + '</span>' +
      '<span class="row__dl">' + esc(dlShort(it)) + '</span></div>' +
      '<div class="row__main">' +
      '<div class="row__title">' + esc(it.title) + '</div>' +
      '<div class="row__meta">' + meta + '</div>' +
      '</div>' +
      '<div class="row__aside">' + badge +
      '<span class="row__amt' + (amt.text ? '' : ' row__amt--none') + '">' +
      (amt.text ? (amt.label ? '<span>' + amt.label + '</span>' : '') + esc(amt.text) : '금액 미확인') +
      '</span></div>' +
      '</article>';
  }

  function resultRow(it) {
    var r = it.result || {};
    var label = r.state === 'opened' ? '개찰완료' : (r.state === 'failed' ? '유찰' : '개찰대기');
    var cls = r.state === 'opened' ? 'pill--opened' : (r.state === 'failed' ? 'pill--failed' : 'pill--pending');
    var winner = r.winner || (r.state === 'failed'
      ? '참가 ' + (r.participants == null ? '?' : r.participants) + '곳 · 유찰'
      : '낙찰자 미확인');
    return '<article class="res" data-id="' + esc(it.id) + '" tabindex="0" role="button">' +
      '<div class="res__main">' +
      '<div class="row__title">' + esc(it.title) + '</div>' +
      '<div class="row__meta"><span class="pill ' + cls + '">' + label + '</span>' +
      '<span class="row__org">' + esc(it.org) + '</span><span class="sep">·</span><span>' + esc(it.no) + '</span>' +
      '<span class="sep">·</span><span>' + esc(it.region) + '</span></div>' +
      '</div>' +
      '<div class="res__n"><b>' + (r.participants == null ? '—' : r.participants) + '</b><small>참가업체</small></div>' +
      '<div class="res__win"><b>' + esc(winner) + '</b><small>' +
      (r.amount ? wonShort(r.amount) + (r.rate ? ' · 낙찰률 ' + r.rate + '%' : '') : (it.open_label ? '개찰 ' + esc(it.open_label) : esc(r.note || ''))) +
      '</small></div>' +
      '</article>';
  }

  function renderList() {
    var rows = filtered();
    var title = state.sido === 'all' ? '전국' : (state.sido === '전국' ? '전국·중앙부처' : state.sido);
    if (state.kind === 'bid') title += ' 입찰공고';
    if (state.kind === 'prespec') title += ' 사전규격';
    if (state.kind === 'result') title += ' 개찰결과';
    if (state.urgentOnly) title = 'D-3 이내 마감';
    if (state.kw !== 'all') title += ' · ' + state.kw;
    $('#listTitle').textContent = title;

    var opens = rows.filter(function (i) { return isOpen(i); }).length;
    $('#listMeta').textContent = rows.length + '건' + (state.includePast ? ' (진행 중 ' + opens + ')' : '');
    $('#resetBtn').hidden = !(state.urgentOnly || state.kw !== 'all' || state.q || state.sido !== 'all' || state.kind !== 'all' || !state.includePast);

    var pastN = scoped().filter(function (i) {
      var dd = ddayOf(i.deadline);
      return dd !== null && dd < 0 && (state.kind === 'all' || (state.kind === 'bid' && i.kind === 'bid') || (state.kind === 'prespec' && i.kind === 'prespec'));
    }).length;
    var pb = $('#pastBtn');
    pb.hidden = state.kind === 'result' || !pastN;
    pb.textContent = state.includePast ? '지난 건 숨기기' : '지난 건 포함 ' + pastN;

    var shown = rows.slice(0, state.limit);
    $('#list').innerHTML = shown.map(state.kind === 'result' ? resultRow : rowHtml).join('');

    var more = $('#list').nextElementSibling;
    if (rows.length > shown.length) {
      var label = '더 보기 (' + (rows.length - shown.length) + '건)';
      if (!more || !more.classList.contains('more')) {
        var div = document.createElement('div');
        div.className = 'more';
        div.innerHTML = '<button class="btn" id="moreBtn" type="button">' + label + '</button>';
        $('#list').after(div);
      } else {
        more.innerHTML = '<button class="btn" id="moreBtn" type="button">' + label + '</button>';
      }
    } else if (more && more.classList.contains('more')) {
      more.remove();
    }

    var empty = $('#emptyState');
    empty.hidden = rows.length > 0;
    if (!rows.length) {
      empty.textContent = pastN
        ? '진행 중인 건이 없습니다. 오른쪽 "지난 건 포함 ' + pastN + '"을 누르면 마감된 건까지 볼 수 있습니다.'
        : '조건에 맞는 건이 없습니다. 시·도를 "전체"로 바꾸거나 검색어를 지워 보세요.';
    }
  }

  /* -------------------------------------------------------------- 드로어 */
  function fileExt(name) {
    var m = /\.([a-z0-9]+)$/i.exec(name || '');
    return m ? m[1].toUpperCase().slice(0, 4) : 'FILE';
  }

  function dedupeAtts(list) {
    var seen = {}, out = [];
    list.forEach(function (f) {
      var key = (f.name || '').trim();
      if (!key) return;
      if (seen[key] == null) { seen[key] = out.length; out.push(f); }
      else if (!out[seen[key]].url && f.url) { out[seen[key]] = f; }
    });
    return out;
  }

  /* ------------------------------------ 드로어: 입찰참가자격 & 입찰 가능 업체 */
  function eligSection(it) {
    var e = it.elig;
    if (!e) {
      return '<div class="qa">업체 매칭 정보가 없습니다. (낙찰사 업등록 DB 빌드 전 공고일 수 있습니다)</div>';
    }
    var v = V(e.verdict);
    var req = e.req || {};
    var selfInds = (DATA.registry && DATA.registry.self_inds) || [];
    var reasons = (e.reasons || []).map(function (r) { return '<li>' + esc(r) + '</li>'; }).join('');
    var inds = (req.industries || []).length
      ? (req.industries || []).map(function (x) { return '<span class="rchip">' + esc(indShort(x)) + '</span>'; }).join('')
      : '<span class="muted small">' + (req.no_industry ? '업종 제한 없음' : '공고문·메타에서 확인 못함') + '</span>';
    var region = (req.region || []).length
      ? (req.region || []).map(function (x) { return '<span class="rchip rchip--area">' + esc(x) + '</span>'; }).join('')
      : '<span class="muted small">제한 없음·미확인</span>';
    var extras = (req.extras || []).length
      ? (req.extras || []).map(function (x) { return '<span class="rchip rchip--etc">' + esc(x) + '</span>'; }).join('')
      : '<span class="muted small">—</span>';
    var srcLabel = { field: '나라장터 공고 메타', note: '공고문 정리 노트' };
    var srcs = (req.sources || []).map(function (s) {
      if (s.indexOf('att:') === 0) return '<span class="rchip rchip--src">첨부 ' + esc(s.slice(4)) + '</span>';
      return '<span class="rchip rchip--src">' + esc(srcLabel[s] || s) + '</span>';
    }).join('') || '<span class="muted small">—</span>';

    var rows = (e.eligible || []).map(function (c) {
      var field = c.field ? ' · ' + esc(c.field) : '';
      return '<div class="ecard">' +
        '<div class="ecard__top"><b>' + esc(c.name) + '</b>' +
        '<span class="ecard__area">' + esc(c.area || '소재지 미확인') + '</span></div>' +
        '<div class="ecard__inds">' + (c.inds || []).map(function (i) {
          return '<span class="rchip rchip--sm">' + esc(indShort(i)) + '</span>';
        }).join('') + '</div>' +
        '<div class="ecard__foot">낙찰 ' + (c.wins || 0) + '건' + field + (c.last ? ' · 최근 ' + esc(String(c.last).slice(0, 7)) : '') + '</div>' +
        '</div>';
    }).join('');

    var more = e.eligible_count > (e.eligible || []).length
      ? '<div class="muted small" style="margin-top:6px">외 ' + (e.eligible_count - (e.eligible || []).length) + '곳 — <b>낙찰사 업등록 DB</b>에서 전체 확인</div>'
      : '';

    return '<div class="eligbox eligbox--' + v.cls + '">' +
      '<div class="eligbox__top"><span class="ebadge ebadge--' + v.cls + '">' + v.mark + ' ' + v.label + '</span>' +
      '<span class="eligbox__who">㈜웨이즈원 입찰</span></div>' +
      (reasons ? '<ul class="eligbox__why">' + reasons + '</ul>' : '') +
      '<div class="eligbox__self"><span class="small muted">당사 보유</span> ' +
      (selfInds.length ? selfInds.map(function (i) { return '<span class="rchip rchip--sm">' + esc(indShort(i)) + '</span>'; }).join('')
        : '<span class="small muted">원부 미확인</span>') + '</div>' +
      '</div>' +
      '<dl class="req">' +
      '<dt>필수 업종</dt><dd>' + inds + '</dd>' +
      '<dt>지역제한</dt><dd>' + region + '</dd>' +
      '<dt>공동수급</dt><dd>' + esc(req.consortium || '미확인') + '</dd>' +
      '<dt>추가 서류·요건</dt><dd>' + extras + '</dd>' +
      '<dt>근거</dt><dd>' + srcs + '</dd>' +
      '</dl>' +
      '<h4 class="sub4">기존 낙찰사 중 단독 입찰 가능 <span class="pill pill--pre">' + (e.eligible_count || 0) + '곳</span></h4>' +
      (rows ? '<div class="ecards">' + rows + '</div>' + more
        : '<div class="qa">' + (e.verdict === '요건미확인'
          ? '참가자격을 확인하지 못해 업체를 매칭하지 않았습니다.'
          : '등록된 낙찰사 중 이 요건을 모두 충족하는 업체가 없습니다.') + '</div>');
  }

  function openDrawer(id) {
    var it = ITEMS.filter(function (i) { return i.id === id; })[0];
    if (!it) return;
    var n = ddayOf(it.deadline);
    var r = it.result || {};
    var amt = amountOf(it);

    var atts = dedupeAtts(it.attachments || []);
    var files = atts.length
      ? atts.map(function (f) {
        var href = f.url || it.links.g2b;
        return '<a class="file" href="' + esc(href) + '" target="_blank" rel="noopener">' +
          '<span class="file__ext">' + esc(fileExt(f.name)) + '</span>' +
          '<span class="file__name">' + esc(f.name) + (f.size ? ' <span class="muted small">' + esc(f.size) + '</span>' : '') + '</span>' +
          '<span class="file__act">' + (f.url ? '내려받기' : '공고 상세') + '</span></a>';
      }).join('')
      : '<div class="qa">' + (it.attachments_checked
        ? '나라장터 공고 상세 확인 결과 <b>첨부파일이 없는 공고</b>입니다(전자시담·수의시담).'
        : (it.kind === 'prespec'
          ? '첨부 규격서 목록은 나라장터 로그인 상세에서 확인할 수 있습니다. 위 <b>나라장터 사전규격</b>을 열어 확인하세요.'
          : '첨부파일 목록을 확인하지 못했습니다. 나라장터 원문에서 확인하세요.')) + '</div>';

    var qnaState = { confirmed: '확인', noted: '일부 확인', none: '등록된 질의 없음', unknown: '미확인' }[it.qna.state] || '미확인';
    var qnaCls = it.qna.state === 'confirmed' || it.qna.state === 'noted' ? 'pill--pre' : 'pill--wait';
    var qnaItems = (it.qna.items || []).map(function (q) {
      var meta = [q.kind, q.writer, q.registered].filter(Boolean).join(' · ');
      return '<div class="qa__item"><b>Q. ' + esc(q.q) + '</b>' +
        (meta ? '<span class="muted small"> ' + esc(meta) + '</span>' : '') +
        (q.body ? '<br><span>' + esc(q.body) + '</span>' : '') +
        '<br><b>A. ' + esc(q.a || '답변 미등록') + '</b></div>';
    }).join('');

    var resultHtml;
    if (it.kind === 'prespec') {
      resultHtml = '<div class="qa">사전규격 단계입니다. 본공고로 전환된 뒤 개찰결과가 표시됩니다.</div>';
    } else if (r.state === 'opened') {
      resultHtml = '<div class="rbox"><div class="rbox__head"><span class="pill pill--opened">개찰완료</span>' +
        (r.opened_at ? '<span class="muted small">개찰 ' + esc(r.opened_at.slice(0, 16).replace('T', ' ')) + '</span>' : '') + '</div>' +
        '<div class="rbox__body"><div class="rgrid">' +
        '<div class="rcell"><span>참가업체</span><b>' + (r.participants == null ? '미확인' : r.participants + '곳') + '</b></div>' +
        '<div class="rcell"><span>낙찰·계약업체</span><b>' + esc(r.winner || '미확인') + '</b></div>' +
        '<div class="rcell"><span>낙찰·계약금액</span><b>' + (r.amount ? wonShort(r.amount) : '미확인') + '</b></div>' +
        '<div class="rcell"><span>낙찰률</span><b>' + (r.rate ? r.rate + '%' : '미공개') + '</b></div>' +
        '</div>' + (r.note ? '<p class="small muted" style="margin:8px 0 0">' + esc(r.note) + '</p>' : '') + '</div></div>';
    } else if (r.state === 'failed') {
      resultHtml = '<div class="rbox"><div class="rbox__head"><span class="pill pill--failed">유찰</span>' +
        '<span class="muted small">' + (r.participants != null ? '참가 ' + r.participants + '곳' : '참가 정보 없음') + '</span></div></div>';
    } else if (r.state === 'pending') {
      resultHtml = '<div class="rbox"><div class="rbox__head"><span class="pill pill--pending">개찰결과 대기</span></div>' +
        '<div class="rbox__body small muted">마감은 지났지만 개찰결과가 아직 등록되지 않았습니다. (' + esc(r.note || '') + ')</div></div>';
    } else {
      resultHtml = '<div class="qa">마감 전입니다. 개찰결과는 개찰 뒤 표시됩니다.</div>';
    }

    var copyTarget = it.kind === 'prespec' ? it.no : it.no + '-' + (it.order || '000');
    var cond = [
      ['계약방법', it.contract || '—'],
      ['지역제한', it.region_limit || '공고문 확인'],
      ['업종제한', it.industry_limit || '공고문 확인'],
      ['참가조건', it.conditions || '공고문 확인']
    ].map(function (p) { return '<dt>' + p[0] + '</dt><dd>' + esc(p[1]) + '</dd>'; }).join('');

    $('#drawer').innerHTML =
      '<div class="dw-head">' +
      '<div class="dw-top">' + kindPill(it) + pillOf(it) +
      '<span class="dd ' + ddayCls(n) + '">' + ddayText(n) + '</span>' +
      '<button class="dw-close" data-close="1" aria-label="닫기">✕</button></div>' +
      '<h2 class="dw-title">' + esc(it.title) + '</h2>' +
      '<div class="dw-sub"><span>' + esc(it.org) + '</span><span>·</span><span>' + esc(it.no) + '</span>' +
      '<span>·</span><span>' + esc(it.region === '전국' ? '전국·중앙부처' : it.region) + '</span></div>' +
      '</div>' +
      '<div class="dw-body">' +
      (it.note ? '<div class="dw-sec"><div class="note">' + esc(it.note) + '</div></div>' : '') +
      '<div class="dw-sec"><div class="stats">' +
      '<div class="stat stat--wide"><span>' + esc(it.deadline_kind) + '</span><b>' + esc(it.deadline_label || '공고문 확인') + '</b>' +
      (it.deadline_note ? '<span class="muted small" style="font-weight:600;margin-top:2px">' + esc(it.deadline_note) + '</span>' : '') + '</div>' +
      '<div class="stat"><span>개찰</span><b>' + esc(it.open_label || '공고문 확인') + '</b></div>' +
      '<div class="stat"><span>추정가격</span><b>' + (it.price_est ? wonShort(it.price_est) : '—') + '</b></div>' +
      '<div class="stat"><span>배정예산</span><b>' + esc(it.budget ? wonShort(it.budget) : (it.budget_text ? String(it.budget_text).replace(/\s*원$/, '') : '—')) + '</b></div>' +
      '</div></div>' +
      '<div class="dw-sec"><h3>참가 조건</h3><dl class="kv">' + cond +
      '<dt>키워드</dt><dd>' + esc((it.keywords || []).join(' · ') || '—') + '</dd></dl></div>' +
      '<div class="dw-sec"><h3>입찰참가자격 · 입찰 가능 업체</h3>' + eligSection(it) + '</div>' +
      '<div class="dw-sec"><h3>첨부파일 <span class="pill pill--wait">' + (atts.length || '미확인') + '</span></h3><div class="files">' + files + '</div></div>' +
      (it.kind === 'prespec' || it.qna.state === 'confirmed' || it.qna.state === 'noted'
        ? '<div class="dw-sec"><h3>사전규격 질의 <span class="pill ' + qnaCls + '">' + qnaState + '</span></h3>' +
          '<div class="qa">' + esc(it.qna.summary || '') + qnaItems + '</div></div>'
        : '') +
      '<div class="dw-sec"><h3>개찰결과</h3>' + resultHtml + '</div>' +
      '<div class="dw-sec"><h3>원문 · 출처</h3><dl class="kv">' +
      '<dt>나라장터</dt><dd><a href="' + esc(it.links.g2b) + '" target="_blank" rel="noopener">' + esc(it.links.g2b_kind || '공고 상세') + ' ↗</a></dd>' +
      (it.links.presignal ? '<dt>수집원</dt><dd><a href="' + esc(it.links.presignal) + '" target="_blank" rel="noopener">presignal 원문 ↗</a></dd>' : '') +
      (it.links.data00 ? '<dt>공공일감</dt><dd><a href="' + esc(it.links.data00) + '" target="_blank" rel="noopener">첨부·개찰 상세 ↗</a></dd>' : '') +
      '</dl></div>' +
      '</div>' +
      '<div class="dw-bar">' +
      '<a class="btn btn--primary" href="' + esc(it.links.g2b) + '" target="_blank" rel="noopener">나라장터 ' + (it.kind === 'prespec' ? '사전규격 열기' : '공고 상세') + '</a>' +
      '<button class="btn" type="button" data-copy="' + esc(copyTarget) + '">공고번호 복사</button>' +
      '<span class="copy-hint" id="copyHint">복사됨</span>' +
      '</div>';

    $('#drawerWrap').hidden = false;
    document.body.style.overflow = 'hidden';
    $('#drawer').scrollTop = 0;
    $('#drawer').focus && $('#drawer').focus();
  }

  function closeDrawer() {
    $('#drawerWrap').hidden = true;
    document.body.style.overflow = '';
  }

  /* ------------------------------------------------ 낙찰사 업등록 DB 모달 */
  var regState = { q: '', field: 'all', sort: 'wins' };

  function regData() { return (DATA && DATA.registry) || null; }

  function renderReg() {
    var reg = regData();
    if (!reg) return;
    var q = regState.q.trim().toLowerCase().replace(/\s+/g, '');
    var rows = (reg.companies || []).filter(function (c) {
      if (regState.field !== 'all' && !(c.fields && c.fields[regState.field])) return false;
      if (!q) return true;
      var hay = [c.name, c.area, c.addr, (c.inds || []).join(' ')].join('').toLowerCase().replace(/\s+/g, '');
      return hay.indexOf(q) >= 0;
    });
    rows.sort(function (a, b) {
      if (regState.sort === 'name') return a.name.localeCompare(b.name, 'ko');
      if (regState.sort === 'amount') return (b.amount || 0) - (a.amount || 0);
      return (b.wins || 0) - (a.wins || 0) || (b.amount || 0) - (a.amount || 0);
    });
    var st = reg.stats || {};
    $('#regMeta').textContent = '업체 ' + (st.companies || rows.length) + '곳 · 측량업 ' + (st.kasm || 0) +
      ' · 엔지니어링 ' + (st.etis || 0) + ' · SW사업자 ' + (st.swit || 0) + ' · ' + (reg.updated_at || '').slice(0, 10) + ' 수집';

    var sel = $('#regField');
    if (!sel.options.length) {
      var fields = {};
      (reg.companies || []).forEach(function (c) { Object.keys(c.fields || {}).forEach(function (f) { fields[f] = (fields[f] || 0) + 1; }); });
      sel.innerHTML = '<option value="all">전체 분야</option>' + Object.keys(fields).sort(function (a, b) { return fields[b] - fields[a]; })
        .map(function (f) { return '<option value="' + esc(f) + '">' + esc(f) + ' (' + fields[f] + ')</option>'; }).join('');
    }

    $('#regBody').innerHTML = rows.length ? rows.map(function (c) {
      var inds = (c.inds || []);
      var chips = inds.slice(0, 5).map(function (i) { return '<span class="rchip rchip--sm">' + esc(indShort(i)) + '</span>'; }).join('') +
        (inds.length > 5 ? '<span class="rchip rchip--sm rchip--more">+' + (inds.length - 5) + '</span>' : '');
      var fields = Object.keys(c.fields || {}).map(function (f) { return esc(f) + ' ' + c.fields[f]; }).join(' · ');
      return '<div class="regrow' + (c.self ? ' regrow--self' : '') + '">' +
        '<div class="regrow__top"><b class="regrow__name">' + esc(c.name) + '</b>' +
        (c.self ? '<span class="pill pill--bid">당사</span>' : '') +
        (c.sw ? '<span class="rchip rchip--sm">' + esc(c.sw) + '</span>' : '') +
        (c.flag ? '<span class="rchip rchip--sm rchip--warn" title="원부 간 소재지 불일치: ' + esc(c.flag.join(', ')) + '">동명이인 주의</span>' : '') +
        '<span class="regrow__area">' + esc(c.area || '소재지 미확인') + '</span></div>' +
        '<div class="regrow__inds">' + (chips || '<span class="muted small">업종 원부 미확인</span>') + '</div>' +
        '<div class="regrow__foot"><span>낙찰 <b>' + (c.wins || 0) + '건</b>' + (c.amount ? ' · ' + wonShort(c.amount) : '') + '</span>' +
        (fields ? '<span class="muted small">' + fields + '</span>' : '') +
        (c.last ? '<span class="muted small">최근 ' + esc(String(c.last).slice(0, 7)) + '</span>' : '') + '</div>' +
        '</div>';
    }).join('') : '<div class="qa">조건에 맞는 업체가 없습니다.</div>';

    var srcs = (reg.sources || {});
    var srcNote = Object.keys(srcs).map(function (k) {
      var s = srcs[k];
      return '<div><b>' + esc(s.name) + '</b> — ' + esc(s.status || (s.method || '') + (s.scope ? ' · ' + s.scope : '')) + '</div>';
    }).join('');
    $('#regBody').innerHTML += '<div class="regsrc"><b>원부 출처</b>' + srcNote + '</div>';
  }

  function openReg() {
    if (!regData()) return;
    $('#regWrap').hidden = false;
    document.body.style.overflow = 'hidden';
    renderReg();
  }

  function closeReg() {
    $('#regWrap').hidden = true;
    document.body.style.overflow = '';
  }

  /* --------------------------------------------------------------- 추적 */
  function renderWatch() {
    var list = DATA.watchlist || [];
    var box = $('#watch');
    if (!list.length) { box.hidden = true; return; }
    box.hidden = false;
    $('#watchN').textContent = list.length + '건';
    $('#watchBody').innerHTML = list.map(function (w) {
      return '<div class="wcard"><b>' + esc(w.label) + ' <span class="pill ' + (w.tone === 'urgent' ? 'pill--pending' : 'pill--wait') + '">' + esc(w.status) + '</span></b>' +
        '<div class="wcard__m">' + esc(w.meta || '') + '</div>' +
        (w.note ? '<div class="wcard__n">' + esc(w.note) + '</div>' : '') +
        (w.g2b ? '<a href="' + esc(w.g2b) + '" target="_blank" rel="noopener">나라장터에서 보기 ↗</a>' : '') +
        '</div>';
    }).join('');
  }

  /* --------------------------------------------------------------- 푸터 */
  function renderFooter() {
    var w = DATA.window || {};
    var c = DATA.counts || {};
    var f = DATA.dashboard_filter || {};
    $('#brandSub').textContent = '전국 · 최근 ' + (w.days || 30) + '일 · ' + (DATA.dashboard_keywords || []).length + '개 키워드';
    $('#foot').innerHTML =
      '<div><b>데이터 기준</b> ' + esc(DATA.updated_label || '') + ' · 조회 구간 ' + esc(w.from || '') + ' ~ ' + esc(w.to || '') + ' (공고일 기준 ' + (w.days || 30) + '일)</div>' +
      '<div><b>수록</b> 입찰공고 ' + (c.bids || 0) + '건 · 사전규격 ' + (c.prespec || 0) + '건 · 첨부 확인 ' + (c.attachments || 0) + '건 · 개찰완료 ' + (c.opened || 0) + '건 · 유찰 ' + (c.failed || 0) + '건</div>' +
      '<div><b>시·도 구분</b> 발주기관 소재 기준입니다. 중앙부처·전국 단위 공기업은 <code>전국·중앙부처</code>로 묶었습니다.</div>' +
      (f.excluded_keywords ? '<div><b>대시보드 제외 키워드</b> ' + esc(f.excluded_keywords.join(' · ')) + ' — 이 키워드만 걸린 ' + (f.excluded_items || 0) + '건은 표시하지 않습니다. 09:00·16:00 정기 스캔과 알림은 14개 키워드 그대로 수집합니다.</div>' : '') +
      '<div><b>출처</b> ' + esc((DATA.scan_basis && DATA.scan_basis.sources) || '') + '</div>' +
      (DATA.eligibility ? '<div><b>입찰가능 매칭</b> 공고 ' + (DATA.eligibility.items || 0) + '건 중 참가자격 파싱 ' + (DATA.eligibility.parsed || 0) + '건 — ' +
        '웨이즈원 <b>참가가능 ' + ((DATA.eligibility.verdicts || {})['가능'] || 0) + '</b> · 조건부 ' + ((DATA.eligibility.verdicts || {})['조건부'] || 0) +
        ' · 불가 ' + ((DATA.eligibility.verdicts || {})['불가'] || 0) + ' · 요건미확인 ' + ((DATA.eligibility.verdicts || {})['요건미확인'] || 0) +
        (DATA.registry ? ' / 낙찰사 업등록 DB ' + ((DATA.registry.stats || {}).companies || 0) + '곳' : '') + '</div>' : '') +
      '<div><b>주의</b> 금액·마감·자격은 수집 시점 정리값입니다. 응찰 판단 전 나라장터 공고문·제안요청서 원문으로 다시 확인하세요. D-day는 접속한 날짜 기준으로 계산되며 30일이 지난 공고는 자동으로 빠집니다.</div>';
  }

  /* --------------------------------------------------------------- 이벤트 */
  function paint() {
    renderSido();
    renderKind();
    renderList();
  }

  function resetAll() {
    state.sido = 'all'; state.kind = 'all'; state.q = ''; state.kw = 'all';
    state.urgentOnly = false; state.limit = PAGE; state.includePast = true;
    $('#q').value = '';
    $('#sortSel').value = 'deadline';
    state.sort = 'deadline';
    paint();
  }

  function bind() {
    $('#sidoNav').addEventListener('click', function (e) {
      var b = e.target.closest('[data-sido]');
      if (!b || b.classList.contains('is-zero')) return;
      state.sido = b.getAttribute('data-sido');
      state.kind = 'all'; state.limit = PAGE; state.urgentOnly = false;
      paint();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    $('#kindSeg').addEventListener('click', function (e) {
      var b = e.target.closest('[data-kind]');
      if (!b) return;
      state.kind = b.getAttribute('data-kind'); state.limit = PAGE;
      renderKind(); renderList();
    });
    $('#kwRow').addEventListener('click', function (e) {
      var b = e.target.closest('[data-kw]');
      if (!b) return;
      state.kw = b.getAttribute('data-kw'); state.limit = PAGE;
      renderKind(); renderList();
    });
    $('#q').addEventListener('input', function (e) {
      state.q = e.target.value; state.limit = PAGE; renderList();
    });
    $('#sortSel').addEventListener('change', function (e) {
      state.sort = e.target.value; state.limit = PAGE; renderList();
    });
    $('#resetBtn').addEventListener('click', resetAll);
    $('#pastBtn').addEventListener('click', function () {
      state.includePast = !state.includePast; state.limit = PAGE; renderList();
    });
    $('#urgent').addEventListener('click', function (e) {
      var all = e.target.closest('#urgentAll');
      if (all) {
        state.urgentOnly = true; state.sido = 'all'; state.kind = 'all'; state.limit = PAGE;
        state.sort = 'deadline'; $('#sortSel').value = 'deadline';
        paint();
        $('#listTitle').scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }
      var row = e.target.closest('[data-id]');
      if (row) openDrawer(row.getAttribute('data-id'));
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
      if (e.target.closest('#moreBtn')) { state.limit += PAGE; renderList(); return; }
      if (e.target.closest('[data-close]')) { closeDrawer(); return; }
      if (e.target.closest('[data-regclose]')) { closeReg(); return; }
      var zero = e.target.closest('.sido__btn.is-zero');
      if (zero) { e.preventDefault(); return; }
      var cp = e.target.closest('[data-copy]');
      if (cp) copyText(cp.getAttribute('data-copy'));
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !$('#regWrap').hidden) { closeReg(); return; }
      if (e.key === 'Escape' && !$('#drawerWrap').hidden) closeDrawer();
    });
    $('#reloadBtn').addEventListener('click', function () { location.reload(); });
    $('#regBtn').addEventListener('click', openReg);
    $('#regQ').addEventListener('input', function (e) { regState.q = e.target.value; renderReg(); });
    $('#regField').addEventListener('change', function (e) { regState.field = e.target.value; renderReg(); });
    $('#regSort').addEventListener('change', function (e) { regState.sort = e.target.value; renderReg(); });
  }

  function copyText(text) {
    var done = function () {
      var h = $('#copyHint');
      if (h) { h.classList.add('show'); setTimeout(function () { h.classList.remove('show'); }, 1600); }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else { fallback(); }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); } catch (err) { window.prompt('공고번호', text); }
      document.body.removeChild(ta);
    }
  }

  /* ----------------------------------------------------------------- boot */
  function boot(data) {
    DATA = data;
    ITEMS = (data.items || []).slice();
    $('#updatedStamp').textContent = (data.updated_label || '') + ' 기준';
    renderFooter();
    renderSido();
    renderUrgent();
    renderKind();
    renderList();
    renderWatch();
    bind();
    var act = $('#sidoNav .is-active');
    if (act && act.scrollIntoView) act.scrollIntoView({ block: 'nearest', inline: 'center' });
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
      fail('데이터를 불러오지 못했습니다 (' + esc(err.message) + ').<br>index.html을 파일로 직접 열었다면 로컬 서버로 여세요: <code>python3 -m http.server 8000</code>');
    });
})();
