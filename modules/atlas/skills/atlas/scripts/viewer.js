/* Atlas/DN: embedded content is data; DOM content is written as text. */
(function () {
  'use strict';
  const DOC_TABS = [['overview', 'Обзор'], ['documents', 'Документы'], ['contracts', 'Контракты'], ['relations', 'Связи'], ['matrix', 'Матрица и события'], ['history', 'Журнал']];
  const ATLAS_TABS = [['works', 'Матрица работ'], ['contracts', 'Контракты'], ['documents', 'Документы'], ['actors', 'Участники'], ['history', 'История'], ['relations', 'Связи'], ['coverage', 'Покрытие']];
  const STATES = {PLANNED: 'Запланировано', DOING: 'В работе', REVIEW: 'На проверке', ACCEPTED: 'Принято', BLOCKED: 'Заблокировано', PAUSED: 'Приостановлено', CANCELLED: 'Отменено', UNKNOWN: 'Не установлено'};
  const ACTIVITY = {CURRENT: 'Активность подтверждена в записанном интервале', EXPIRED: 'Период подтверждения активности истёк', UNKNOWN: 'Текущая активность не установлена'};
  const arr = value => Array.isArray(value) ? value : [];
  const textValue = value => value === undefined || value === null || value === '' ? 'UNKNOWN' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const searchable = (value, query) => JSON.stringify(value).toLocaleLowerCase('ru').includes(String(query || '').toLocaleLowerCase('ru'));
  const works = s => arr(s.atlas && s.atlas.works);
  const entities = s => [...arr(s.documents), ...arr(s.input.modules), ...arr(s.input.contracts)];
  const find = (s, id) => entities(s).find(x => x.id === id);
  const findWork = (s, id) => works(s).find(x => x.id === id);
  function actors(item) {
    return [...new Set([item.writer, ...[].concat(item.assigned_to || []), item.activity && item.activity.actor,
      ...arr(item.events).map(x => x.actor), ...arr(item.evidence).map(x => x.actor), ...arr(item.acceptance).map(x => x.actor),
      ...arr(item.derived && item.derived.completed_by)].filter(x => typeof x === 'string' && x))];
  }
  function belongs(s, item, moduleId) {
    if (!moduleId) return true;
    if (!item) return false;
    if (item.id === moduleId || item.module === moduleId) return true;
    const owner = arr(s.input.modules).find(x => x.id === moduleId);
    return !!owner && (arr(owner.docs).includes(item.id) || arr(s.input.contracts).some(c => c.module === moduleId && arr(c.docs).includes(item.id)));
  }
  function selected(s, item, state) {
    return (!item.lifecycle || state.lifecycle === 'all' || item.lifecycle === (state.lifecycle || 'current'))
      && belongs(s, item, state.module) && searchable(item, state.query);
  }
  // The stored assessment is authoritative. The clock may expire it, never establish activity.
  function activityState(item, now = Date.now(), previous) {
    const declared = item.derived && item.derived.activity_state;
    if (declared === 'EXPIRED' || previous === 'EXPIRED') return 'EXPIRED';
    if (declared !== 'CURRENT' || previous === 'UNKNOWN') return 'UNKNOWN';
    const a = item.activity;
    const until = a && Date.parse(a.valid_until), observed = a && Date.parse(a.observed_at);
    if (!a || !Number.isFinite(until) || !Number.isFinite(observed) || observed > until || observed > now || !Number.isFinite(now)) return 'UNKNOWN';
    return now >= until ? 'EXPIRED' : 'CURRENT';
  }
  function criterionProgress(item) {
    const d = item.derived || {};
    return Number.isInteger(d.accepted_criteria) && Number.isInteger(d.total_criteria)
      && d.accepted_criteria >= 0 && d.total_criteria >= d.accepted_criteria
      ? `${d.accepted_criteria} / ${d.total_criteria}` : 'UNKNOWN';
  }
  function atlasRelations(s) {
    const rows = arr(s.input.relations).map(x => ({...x, atlas_relation: 'document'}));
    works(s).forEach(w => {
      if (w.parent_id) rows.push({from: w.id, to: w.parent_id, type: 'Дочерняя работа → родитель', atlas_relation: 'work'});
      arr(w.depends_on).forEach(id => rows.push({from: w.id, to: id, type: 'Зависит от работы', atlas_relation: 'work'}));
      arr(w.artifacts).forEach(a => {
        arr(a.entity_ids).forEach(id => rows.push({from: w.id, to: id, type: `Artifact · ${a.role}`, atlas_relation: 'artifact', artifact: a}));
        if (a.patch) rows.push({from: w.id, to: a.patch.target_id, type: 'Патч артефакта', atlas_relation: 'patch', artifact: a});
      });
    });
    return rows;
  }
  function derive(s, state) {
    if (state.tab === 'works') return works(s).filter(x => (!state.workState || state.workState === 'all' || x.state === state.workState)
      && (!state.actor || actors(x).includes(state.actor)) && searchable(x, state.query));
    if (state.tab === 'matrix') return (s.matrix_snapshot ? [...arr(s.matrix_snapshot.steps).map(x => ({...x, matrix_kind: 'step'})), ...arr(s.matrix_snapshot.events).map(x => ({...x, matrix_kind: 'event'}))] : []).filter(x => searchable(x, state.query));
    if (state.tab === 'history') {
      const rows = arr(s.input.history).slice();
      if (s.atlas) {
        works(s).forEach(w => arr(w.events).forEach(event => rows.push({...event, atlas_work_id: w.id, atlas_work_title: w.title, atlas_display_title: workDisplayTitle(buildPresentation(s),w)})));
        rows.sort((a, b) => (Date.parse(b.at) || 0) - (Date.parse(a.at) || 0));
      }
      return rows.filter(x => searchable(x, state.query));
    }
    if (state.tab === 'relations') {
      if (s.atlas) return atlasRelations(s).filter(edge => searchable([edge, find(s, edge.from), find(s, edge.to), findWork(s, edge.from), findWork(s, edge.to)], state.query));
      return arr(s.input.relations).filter(edge => {
        const a = find(s, edge.from), b = find(s, edge.to);
        return (!state.module || belongs(s, a, state.module) || belongs(s, b, state.module))
          && [a, b].every(x => x && (!x.lifecycle || state.lifecycle === 'all' || x.lifecycle === (state.lifecycle || 'current')))
          && searchable([edge, a && a.title, b && b.title], state.query);
      });
    }
    const source = state.tab === 'contracts' ? arr(s.input.contracts) : state.tab === 'documents' ? arr(s.documents) : arr(s.input.modules);
    return source.filter(x => selected(s, x, state));
  }
  function reset(state) { return Object.assign(state, {query: '', module: '', lifecycle: 'current', selection: null, selectionKind: null, workState: 'all', actor: '', activeOnly: false}); }
  function openWork(s, state, id) {
    if (!findWork(s, id)) return false;
    reset(state); state.selection = id; state.selectionKind = 'work'; state.tab = 'works'; return true;
  }
  function openEntity(s, state, id) {
    const item = find(s, id);
    if (!item) return openWork(s, state, id);
    reset(state); state.selection = id; state.selectionKind = 'entity';
    state.lifecycle = item.lifecycle || 'current';
    state.tab = arr(s.documents).some(d => d.id === id) ? 'documents' : arr(s.input.contracts).some(c => c.id === id) ? 'contracts' : 'overview';
    return true;
  }
  function exportIndex(s) { return s.input; }
  // Presentation reads the already pinned owning document. It never rewrites Atlas decisions.
  const PRESENTATION = 'ATLAS-READABLE-1.0.0';
  const SOURCE_STATES = {done: 'Выполнено', doing: 'В работе (по журналу)', partial: 'Частично', waiting: 'Ожидает', planned: 'Запланировано', blocked: 'Заблокировано', paused: 'Приостановлено', cancelled: 'Отменено'};
  const SOURCE_ROLES = ['executor_ids', 'contributor_ids', 'reviewer_ids', 'history_ids', 'coordinator_id'];
  const modelCache = new WeakMap();
  function matrixSource(s) {
    const a = s.atlas || {}, p = a.presentation, docs = arr(s.documents);
    let candidates;
    if (p) {
      if (p.source_matrix_status !== 'PINNED') return {status: p.source_matrix_status || 'UNAVAILABLE', document: null, data: null};
      candidates = docs.filter(d => d.id === p.source_matrix_doc_id && d.sha256 === p.source_matrix_sha256 && d.lifecycle === 'current');
    } else {
      const source = a.project && a.project.source_ref;
      const divider = typeof source === 'string' ? source.indexOf(' pointer=') : -1;
      const sourcePath = divider < 0 ? source : source.slice(0, divider), pointer = divider < 0 ? '' : source.slice(divider + 9);
      const marker = typeof source === 'string' ? sourcePath + ' [owning matrix projection source]' : null;
      const expectedRefs = pointer ? [marker + ' pointer=' + pointer] : [marker, marker + ' pointer='];
      candidates = typeof source === 'string' ? docs.filter(d => d.lifecycle === 'current'
        && expectedRefs.includes(d.source_ref)
        && arr(a.source_pins).some(pin => pin.path === d.path && pin.sha256 === d.sha256 && pin.bytes === d.bytes)) : [];
    }
    if (candidates.length !== 1) return {status: candidates.length > 1 ? 'AMBIGUOUS' : 'UNAVAILABLE', document: null, data: null};
    const doc = candidates[0];
    try {
      const data = JSON.parse(doc.content);
      if (!data || typeof data !== 'object' || typeof data.schema !== 'string' || !Array.isArray(data.steps) || !Array.isArray(data.events)) throw Error('shape');
      const ids = new Set();
      for (const step of data.steps) {
        if (!step || typeof step.id !== 'string' || ids.has(step.id)) throw Error('step identity');
        ids.add(step.id);
      }
      return {status: 'PINNED', document: doc, data};
    } catch (_) { return {status: 'INVALID_DOCUMENT', document: doc, data: null}; }
  }
  function eventOrder(values) {
    return arr(values).map((value, index) => ({value, index})).sort((a, b) => {
      const ta = Date.parse(a.value.at), tb = Date.parse(b.value.at);
      return (Number.isFinite(ta) ? ta : -Infinity) - (Number.isFinite(tb) ? tb : -Infinity) || a.index - b.index;
    }).map(x => x.value);
  }
  function effective(values, at) { return eventOrder(values).filter(e => Number.isFinite(Date.parse(e.at)) && Date.parse(e.at) <= at); }
  function verifiedTitleRecords(s, model) {
    // Work titles are display-only; no fuzzy names or permission inference.
    const metadata = s?.atlas?.localized_titles, out = new Map();
    if (!metadata || metadata.schema !== 'atlas.localized-work-titles/v1'
        || metadata.language !== 'ru' || metadata.status !== 'PINNED'
        || !Array.isArray(metadata.records) || metadata.records.length > model.byId.size) return out;
    const docById = new Map(arr(s.documents).map(d => [d.id,d]));
    const cache = new Map();
    const eventById = new Map(arr(model.matrix && model.matrix.events).map(e => [e.id,e]));
    for (const rec of metadata.records) {
      if (!rec || typeof rec.work_id !== 'string' || out.has(rec.work_id)) continue;
      const work = model.byId.get(rec.work_id), doc = docById.get(rec.document_id);
      if (!work || !doc || doc.kind !== 'json' || doc.lifecycle !== 'current'
          || rec.original_title !== work.title || typeof rec.title !== 'string'
          || rec.title.trim().length === 0 || rec.title.length > 400 || /[\u0000-\u001f]/u.test(rec.title)
          || rec.document_path !== doc.path || rec.document_sha256 !== doc.sha256
          || rec.document_bytes !== doc.bytes || rec.source_ref !== doc.source_ref
          || rec.json_pointer !== '#/contexts/' + rec.work_id.replace(/~/gu,'~0').replace(/\//gu,'~1')
          || !arr(s.atlas.source_pins).some(p => p.path === doc.path && p.sha256 === doc.sha256 && p.bytes === doc.bytes)
          || !arr(work.artifacts).some(a => arr(a.entity_ids).includes(doc.id))) continue;
      const ev = eventById.get(rec.origin_event_id), hc=ev?.handoff_context, ref=hc?.full_text_ref;
      if (!ev || ev.step_id !== work.id || !ref ||
          ref.json_pointer !== rec.json_pointer.slice(1) || ref.document_id !== rec.origin_document_id
          || hc.display_title !== rec.title) continue;
      if (!cache.has(doc.id)) {
        try { cache.set(doc.id, JSON.parse(doc.content)); }
        catch (_) { cache.set(doc.id,null); }
      }
      const body = cache.get(doc.id), exact = body?.contexts?.[work.id];
      if (!body || body.language !== 'ru' || !exact || exact.work_id !== work.id
          || exact.original_title !== work.title || exact.display_title !== rec.title
          || exact.language !== 'ru') continue;
      out.set(work.id, rec);
    }
    return out;
  }
  // Display-only captions for the exact existing importer-created metadata
  // card. Historical work/event bytes, writer, statuses and authority remain raw.
  const GAP_CARD_ORIGINAL = Object.freeze({
    title: 'Register the next required missing binding',
    outcome: 'Exact project inventory, outcome/criteria and write scopes are linked by the existing writer; every unresolved gap remains explicit.',
    remaining: 'The register describes missing native metadata; preserved source results and prior scoped acceptance remain available. It does not reopen completed work.',
    next_action: 'Register the next missing binding needed by an assigned change. Add the exact module/contract/document once; reuse earlier scoped evidence and do not requalify unchanged historical works.'
  });
  const GAP_CARD_RUSSIAN = Object.freeze({
    title: 'Зарегистрировать следующую необходимую недостающую привязку',
    outcome: 'Точный инвентарь проекта, результаты и критерии, а также области записи связаны действующим владельцем записи; каждый нерешённый пробел обозначен явно.',
    remaining: 'Реестр описывает недостающие исходные метаданные. Сохранённые результаты и прежняя ограниченная приёмка остаются доступны. Завершённые работы не переоткрываются.',
    next_action: 'Зарегистрировать следующую привязку, необходимую для порученного изменения. Однократно добавить точный модуль, контракт или документ; повторно использовать прежние доказательства и не перепроверять неизменившиеся исторические работы.'
  });
  function gapCardCaption(work) {
    if (!work || work.id !== 'ATLAS-IMPORT-GAPS' || work.schema !== 'atlas.work/v1'
        || work.parent_id !== null || !work.next_action
        || work.next_action.actor !== work.writer
        || work.title !== GAP_CARD_ORIGINAL.title
        || work.outcome !== GAP_CARD_ORIGINAL.outcome
        || work.remaining !== GAP_CARD_ORIGINAL.remaining
        || work.next_action.action !== GAP_CARD_ORIGINAL.next_action) return null;
    return GAP_CARD_RUSSIAN;
  }
  function workDisplayField(work, field) {
    const caption = gapCardCaption(work);
    if (caption && Object.prototype.hasOwnProperty.call(caption, field)) return caption[field];
    return field === 'next_action' ? work?.next_action?.action : work?.[field];
  }
  // Exact current-document display projection; raw source records remain authoritative.
  function hasLocalizedFields(s){return !!s.atlas?.localized_fields && s.atlas.localized_fields.status!=='UNAVAILABLE';}
  function displaySHA(text) {
    const input = new TextEncoder().encode(text), size = Math.ceil((input.length + 9) / 64) * 64;
    const data = new Uint8Array(size); data.set(input); data[input.length] = 128;
    new DataView(data.buffer).setUint32(size - 4, input.length * 8, false);
    const k = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    const h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19], w = new Uint32Array(64);
    const rotate = (x,n) => (x >>> n) | (x << (32-n)), view = new DataView(data.buffer);
    for (let offset=0;offset<size;offset+=64) {
      for(let i=0;i<16;i++)w[i]=view.getUint32(offset+i*4,false);
      for(let i=16;i<64;i++){const a=w[i-15],b=w[i-2];w[i]=w[i-16]+(rotate(a,7)^rotate(a,18)^(a>>>3))+w[i-7]+(rotate(b,17)^rotate(b,19)^(b>>>10));}
      let [a,b,c,d,e,f,g,j]=h;
      for(let i=0;i<64;i++){const t1=(j+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^(~e&g))+k[i]+w[i])>>>0,t2=((rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&b)^(a&c)^(b&c)))>>>0;j=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;}
      [a,b,c,d,e,f,g,j].forEach((x,i)=>h[i]=(h[i]+x)>>>0);
    }
    return h.map(x=>x.toString(16).padStart(8,'0')).join('');
  }
  function displayOriginal(model,id,field) {
    if(field.startsWith('project.'))return id===model.project.id?model.project[field.slice(8)]:undefined;
    const w=model.byId.get(id);if(!w)return undefined;
    return field==='work.scope_note'?model.sourceSteps.get(id)?.scope_note:w[field.slice(5)];
  }
  function verifiedDisplayFields(s,model) {
    const metadata=s.atlas?.localized_fields,out=new Map(),invalid=new Set(),issues=[];
    const key=(id,field)=>JSON.stringify([id,field]);
    if(!metadata)return {out,invalid,issues,unknown:false};
    const fields=new Set(['work.title','work.objective','work.scope_note','project.objective','project.scope_note']);
    if(metadata.schema!=='atlas.localized-display-fields/v1'||metadata.language!=='ru'||metadata.project_id!==model.project.id||!Array.isArray(metadata.records)||metadata.records.length>2000||!['PINNED','PARTIAL','UNKNOWN','UNAVAILABLE'].includes(metadata.status)||(metadata.status==='UNAVAILABLE'&&metadata.records.length))
      return {out,invalid,issues:['DISPLAY_METADATA_SCHEMA'],unknown:true};
    for(const bad of arr(metadata.invalid))if(typeof bad.target_id==='string'&&fields.has(bad.field))invalid.add(key(bad.target_id,bad.field));else issues.push(bad.reason||'UNKNOWN_DOCUMENT');
    const seen=new Set(),docs=new Map(arr(s.documents).map(d=>[d.id,d])),cache=new Map();
    for(const r of metadata.records){
      if(!r||typeof r.target_id!=='string'||!fields.has(r.field)){issues.push('UNKNOWN_RECORD');continue;}
      const id=key(r.target_id,r.field);if(seen.has(id)){invalid.add(id);out.delete(id);continue;}seen.add(id);
      try{
        const d=docs.get(r.document_id),original=displayOriginal(model,r.target_id,r.field);
        if(!d||!['md','markdown'].includes(d.kind)||d.lifecycle!=='current'||typeof d.content!=='string'||d.content.length>2097152||typeof original!=='string'||r.original_value!==original||r.original_sha256!==displaySHA(original)||typeof r.translated_value!=='string'||!r.translated_value.trim()||r.translated_value.length>20000||/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(r.translated_value)||r.document_path!==d.path||r.document_sha256!==d.sha256||r.document_bytes!==d.bytes||r.source_ref!==d.source_ref||!arr(s.atlas.source_pins).some(p=>p.path===d.path&&p.sha256===d.sha256&&p.bytes===d.bytes))throw Error('DISPLAY_ID_OR_PIN');
        if(!cache.has(d.id)){
          if(!Number.isSafeInteger(d.bytes)||new TextEncoder().encode(d.content).length!==d.bytes||displaySHA(d.content)!==d.sha256)throw Error('DISPLAY_CONTENT_PIN');
          const begin='<!-- ATLAS_DISPLAY_FIELDS_BEGIN -->',end='<!-- ATLAS_DISPLAY_FIELDS_END -->';
          if(d.content.split(begin).length!==2||d.content.split(end).length!==2)throw Error('DISPLAY_SECTION_COUNT');
          const section=d.content.split(begin)[1].split(end)[0],match=/^\s*```json\r?\n([\s\S]*?)\r?\n```\s*$/u.exec(section);
          if(!match)throw Error('DISPLAY_SECTION_FORMAT');
          const body=JSON.parse(match[1]);
          if(body.schema!==metadata.schema||body.language!=='ru'||body.project_id!==model.project.id||!Array.isArray(body.records)||body.records.length>2000)throw Error('DISPLAY_SECTION_SCHEMA');
          cache.set(d.id,body);
        }
        const match=/^#\/records\/(0|[1-9]\d*)$/u.exec(r.json_pointer),body=cache.get(d.id),exact=match&&body.records[Number(match[1])];
        if(!exact||!['target_id','field','original_value','original_sha256','translated_value'].every(f=>exact[f]===r[f])||Object.keys(exact).length!==5)throw Error('DISPLAY_RECORD_POINTER');
        if(body.records.filter(x=>x?.target_id===r.target_id&&x?.field===r.field).length!==1)throw Error('DISPLAY_DUPLICATE');
        if(!invalid.has(id))out.set(id,r);
      }catch(_){invalid.add(id);out.delete(id);}
    }
    return {out,invalid,issues,unknown:issues.length>0||metadata.status==='UNKNOWN'};
  }
  function displayField(model,id,field) {
    const original=displayOriginal(model,id,field),key=JSON.stringify([id,field]),data=model.localizedFields;
    const legacy=field==='work.title'?model.localizedTitles.get(id):null;
    if(legacy)return {value:legacy.title,original,status:'PINNED_LEGACY_TITLE',provenance:legacy};
    if(data?.invalid.has(key))return {value:original,original,status:'UNKNOWN',provenance:null};
    const rec=data?.out.get(key);
    if(rec)return {value:rec.translated_value,original,status:'PINNED',provenance:rec};
    if(field==='work.objective'){
      const w=model.byId.get(id),step=model.sourceSteps.get(id);
      if(w&&step&&w.objective===w.title&&!(typeof step.source_definition==='string'&&step.source_definition)){
        const title=displayField(model,id,'work.title');
        if(title.status.startsWith('PINNED'))return {value:title.value,original,status:'DERIVED_TITLE_NOT_SEPARATE_OBJECTIVE',provenance:title.provenance};
        if(title.status==='UNKNOWN')return {value:original,original,status:'UNKNOWN',provenance:null};
      }
    }
    return {value:original,original,status:data?.unknown?'UNKNOWN':'ORIGINAL',provenance:null};
  }
  function displayText(model,id,field) {
    const v=displayField(model,id,field);
    return v.status==='UNKNOWN'?'UNKNOWN · перевод не подтверждён · '+textValue(v.original):v.value;
  }
  function displayWorkProjection(model,work){
    return {title:displayField(model,work.id,'work.title'),objective:displayField(model,work.id,'work.objective'),scope_note:displayField(model,work.id,'work.scope_note')};
  }
  function displayProjectProjection(model){
    return {objective:displayField(model,model.project.id,'project.objective'),scope_note:displayField(model,model.project.id,'project.scope_note')};
  }
  function workDisplayTitle(model, work) {
    if (!work) return 'UNKNOWN';
    return model?.localizedTitles?.get(work.id)?.title || (model && (model.localizedFields.out.has(JSON.stringify([work.id,'work.title'])) || model.localizedFields.invalid.has(JSON.stringify([work.id,'work.title'])) || model.localizedFields.unknown) ? displayText(model,work.id,'work.title') : null) || gapCardCaption(work)?.title || work.title;
  }
  function buildPresentation(s) {
    if (modelCache.has(s)) return modelCache.get(s);
    const source = matrixSource(s), matrix = source.data, at = Date.parse(s.atlas && s.atlas.as_of);
    const sourceSteps = new Map(arr(matrix && matrix.steps).map((step, index) => [step.id, {...step, _sourceIndex: index}]));
    const byId = new Map(works(s).map(w => [w.id, w])), children = new Map([[null, []]]), parent = new Map(), eventMap = new Map(), ownership = new Map();
    const roster = arr(matrix && matrix.actors), validActors = roster.filter(a => a && typeof a === 'object' && typeof a.id === 'string' && a.id);
    const participants = new Map(validActors.map(a => [a.id, {...a}]));
    effective(matrix && matrix.actor_updates, at).forEach(update => {
      const actor = participants.get(update.actor_id); if (!actor) return;
      ['label', 'role', 'session_title', 'session_url', 'history_note', 'activity_eligible'].forEach(k => { if (Object.prototype.hasOwnProperty.call(update, k)) actor[k] = update[k]; });
    });
    works(s).forEach(w => {
      const step = sourceSteps.get(w.id), declaredParent = step ? step.parent_id : w.parent_id;
      parent.set(w.id, byId.has(declaredParent) ? declaredParent : null);
      if (!children.has(w.id)) children.set(w.id, []);
      const events = eventOrder(arr(matrix && matrix.events).filter(e => e.step_id === w.id));
      eventMap.set(w.id, events);
      const own = {executor_ids: [], contributor_ids: [], reviewer_ids: [], history_ids: [], coordinator_id: null};
      const recorded = effective(events, at);
      SOURCE_ROLES.forEach(key => {
        const found = recorded.slice().reverse().find(e => Object.prototype.hasOwnProperty.call(e, key));
        if (found) own[key] = found[key];
      });
      ownership.set(w.id, own);
      actors(w).forEach(id => { if (id !== 'UNKNOWN' && !participants.has(id)) participants.set(id, {id, label: id, role: 'Роль не указана', session_url: null}); });
    });
    // Malformed parent cycles cannot hang a page; preserve the source and expose the issue.
    const issues = roster.length === validActors.length ? [] : ['Invalid optional participant entries remain in the source export; only declared actor identities are displayed'];
    parent.forEach((p, id) => {
      const seen = new Set([id]); let cursor = p;
      while (cursor !== null) {
        if (seen.has(cursor)) { parent.set(id, null); issues.push(`Parent cycle at ${id}; source record retained`); break; }
        seen.add(cursor); cursor = parent.get(cursor) ?? null;
      }
    });
    parent.forEach((p, id) => { if (!children.has(p)) children.set(p, []); children.get(p).push(id); });
    const ordinal = new Map(works(s).map((w, i) => [w.id, i]));
    children.forEach(ids => ids.sort((a, b) => {
      const sa = sourceSteps.get(a), sb = sourceSteps.get(b);
      if (sa && !sb) return -1; if (!sa && sb) return 1;
      return (sa && Number.isFinite(sa.order) ? sa.order : ordinal.get(a)) - (sb && Number.isFinite(sb.order) ? sb.order : ordinal.get(b))
        || (sa ? sa._sourceIndex : ordinal.get(a)) - (sb ? sb._sourceIndex : ordinal.get(b));
    }));
    const sourceLatest = new Map([...eventMap].map(([id, events]) => [id, effective(events, at).slice(-1)[0] || null]));
    // Lookup retains saved exact-step observations, independently of activity qualification.
    const observationMap = new Map();
    arr(matrix && matrix.activity_events).forEach(e => {
      if (!e || typeof e !== 'object' || !byId.has(e.step_id)) return;
      if (!observationMap.has(e.step_id)) observationMap.set(e.step_id, []);
      observationMap.get(e.step_id).push(e);
    });
    const observedByActor = new Map();
    effective(matrix && matrix.activity_events, at).forEach(e => observedByActor.set(e.actor_id, e));
    const actorLatest = new Map(), actorEvents = new Map();
    effective(matrix && matrix.actor_events, at).forEach(e => {
      actorLatest.set(e.actor_id, e);
      if (!actorEvents.has(e.actor_id)) actorEvents.set(e.actor_id, []);
      actorEvents.get(e.actor_id).push(e);
    });
    const model = {source, matrix, at, sourceSteps, byId, children, parent, eventMap, ownership, participants, sourceLatest, observationMap, observedByActor, actorLatest, actorEvents, issues};
    model.project = s.atlas?.project || {};
    model.localizedTitles = verifiedTitleRecords(s, model);
    model.localizedFields = verifiedDisplayFields(s, model);
    const absent = [...sourceSteps.keys()].filter(id => !byId.has(id));
    if (absent.length) issues.push(`Source steps without Atlas work records: ${absent.join(', ')}`);
    modelCache.set(s, model); return model;
  }
  function sourceActors(model, id) {
    const own = model.ownership.get(id) || {};
    const ids = SOURCE_ROLES.flatMap(k => [].concat(own[k] || []));
    arr(model.eventMap.get(id)).forEach(e => SOURCE_ROLES.forEach(k => ids.push(...[].concat(e[k] || []))));
    return [...new Set(ids.filter(x => typeof x === 'string' && x))];
  }
  function observationActors(model, id) {
    return [...new Set(arr(model.observationMap.get(id)).map(e => e.actor_id).filter(id => typeof id === 'string' && id && id !== 'UNKNOWN'))];
  }
  function journalDoing(model, item) {
    return item.state === 'DOING' || (model.sourceLatest.get(item.id) || {}).status === 'doing';
  }
  function sourceActivity(model, id, now = Date.now(), previous) {
    if (previous === 'EXPIRED') return {state: 'EXPIRED', observations: [], reason: 'Срок записанного наблюдения истёк'};
    if (!model.matrix || !Number.isFinite(model.at)) return {state: 'UNKNOWN', observations: [], reason: 'Нет закреплённой оценки активности источника'};
    if (arr(model.children.get(id)).length) return {state: 'UNKNOWN', observations: [], reason: 'Активность относится к конечному шагу, а не родителю'};
    const observations = [...model.observedByActor.values()].filter(e => e.step_id === id && e.state === 'active');
    const valid = observations.filter(e => {
      const actor = model.participants.get(e.actor_id), start = Date.parse(e.at), end = Date.parse(e.valid_until);
      const proof = arr(e.evidence).some(p => p && typeof p === 'object'
        && ['supported_native_route', 'supported_native_wait', 'collaboration', 'supported_command'].includes(p.source)
        && typeof p.ref === 'string' && p.ref.trim() && !/[\x00-\x1f]/.test(p.ref)
        && (p.actor_id === undefined || p.actor_id === e.actor_id) && (p.step_id === undefined || p.step_id === e.step_id));
      // A stop invalidates the old observation permanently; a later restart requires a new observation.
      const stopped = arr(model.actorEvents.get(e.actor_id)).some(event => Date.parse(event.at) >= start
        && ['done', 'completed', 'stopped', 'cancelled', 'canceled', 'idle', 'paused', 'terminated'].includes(String(event.state).toLowerCase()));
      const superseded = arr(model.eventMap.get(id)).some(event => Date.parse(event.at) >= start && Date.parse(event.at) <= model.at
        && ['done', 'waiting', 'planned', 'cancelled', 'paused', 'blocked', 'review', 'stopped', 'completed'].includes(String(event.status).toLowerCase()));
      return actor && actor.activity_eligible !== false && model.sourceSteps.has(id) && proof
        && Number.isFinite(start) && Number.isFinite(end) && start <= model.at && start <= now && start < end && end - start <= 3600000
        && !stopped && !superseded;
    });
    if (!valid.length) return {state: 'UNKNOWN', observations, reason: 'Нет подходящего наблюдения по точному шагу в источнике'};
    const freshAtCapture = valid.filter(e => Date.parse(e.valid_until) > model.at);
    if (!freshAtCapture.length) return {state: 'EXPIRED', observations: valid, reason: 'Период наблюдения истёк уже на момент снимка'};
    const fresh = freshAtCapture.filter(e => Number.isFinite(now) && Date.parse(e.valid_until) > now);
    return fresh.length ? {state: 'CURRENT', observations: fresh, reason: 'Наблюдение подтверждено источником в пределах срока; runtime независимо не проверен'}
      : {state: 'EXPIRED', observations: freshAtCapture, reason: 'Срок записанного наблюдения истёк'};
  }
  function roadmapRows(s, state, now = Date.now()) {
    const model = buildPresentation(s), matches = new Set(), visible = new Set();
    const query = String(state.query || '').toLocaleLowerCase('ru');
    model.byId.forEach((w, id) => {
      const sourceIds = sourceActors(model, id);
      const currentSource = state.activeOnly ? sourceActivity(model, id, now, state.agedSourceActivity && state.agedSourceActivity.get(id)) : null;
      const currentNative = state.activeOnly && ownerNativeCurrent(model, w, now, state.agedActivity && state.agedActivity.get(id));
      const actorIds = state.activeOnly ? [...new Set([
        ...(currentSource.state === 'CURRENT' ? currentSource.observations.map(e => e.actor_id) : []),
        ...(currentNative && typeof w.activity?.actor === 'string' ? [w.activity.actor] : [])
      ])] : [...new Set([...actors(w), ...sourceIds, ...observationActors(model, id)])];
      const text = [workDisplayTitle(model,w), w, model.sourceSteps.get(id), model.eventMap.get(id), model.observationMap.get(id), actorIds, actorIds.map(a => model.participants.get(a))];
      const stateMatch = !state.workState || state.workState === 'all' || (state.workState === 'journal:doing' ? journalDoing(model, w)
        : state.workState.startsWith('source:') ? (model.sourceLatest.get(id) || {}).status === state.workState.slice(7) : w.state === state.workState);
      const activityMatch = !state.activeOnly || currentNative || currentSource.state === 'CURRENT';
      if (stateMatch && activityMatch && (!state.actor || actorIds.includes(state.actor)) && (!query || searchable(text, query))) matches.add(id);
    });
    matches.forEach(id => { let p = id; while (p !== null && !visible.has(p)) { visible.add(p); p = model.parent.get(p) ?? null; } });
    const filtering = !!(query || state.actor || state.activeOnly || state.workState && state.workState !== 'all');
    const expanded = state.expanded instanceof Set ? state.expanded : new Set(model.byId.keys());
    const rows = [], stack = arr(model.children.get(null)).slice().reverse().map(id => [id, 0]);
    while (stack.length) {
      const [id, depth] = stack.pop(); if (!visible.has(id)) continue;
      const children = arr(model.children.get(id));
      rows.push({item: model.byId.get(id), id, depth, children, context_only: !matches.has(id), metadata_only: !!model.matrix && !model.sourceSteps.has(id)});
      const open = filtering ? !(state.filterCollapsed && state.filterCollapsed.has(id)) : expanded.has(id);
      if (open) children.slice().reverse().forEach(child => stack.push([child, depth + 1]));
    }
    return {rows, matches: matches.size, total: model.byId.size};
  }
  function presentationHistory(s) {
    const model = buildPresentation(s), result = [];
    [['events', 'Событие работы из источника'], ['actor_events', 'Событие участника из источника'], ['actor_updates', 'Изменение роли в источнике'], ['activity_events', 'Наблюдение активности в источнике']].forEach(([key, origin]) => {
      arr(model.matrix && model.matrix[key]).forEach((raw, index) => result.push({origin, id: raw.id, at: raw.at, actor: raw.actor_id || raw.coordinator_id,
        atlas_work_id: raw.step_id, kind: raw.kind || raw.status || raw.state || origin, summary: raw.note || raw.role || raw.observation || '', raw, source_index: index}));
    });
    derive(s, {tab: 'history', query: ''}).forEach(raw => result.push({...raw, origin: raw.atlas_work_id ? 'Событие работы Atlas' : 'Событие документа', raw}));
    return eventOrder(result).reverse();
  }
  function routeFor(tab, id) {
    const routes = {works: 'roadmap', actors: 'actors', overview: 'modules'};
    return '#' + (routes[tab] || tab) + (id === undefined || id === null ? '' : '/' + encodeURIComponent(id));
  }
  function parseRoute(hash, s) {
    const raw = String(hash || '').replace(/^#/, ''), pieces = raw.split('/'), name = pieces.shift() || 'roadmap';
    let id; try { id = pieces.length ? decodeURIComponent(pieces.join('/')) : null; } catch (_) { return {error: 'Неверная ссылка', tab: 'works'}; }
    const sections = {roadmap: 'works', works: 'works', contracts: 'contracts', documents: 'documents', actors: 'actors', history: 'history', relations: 'relations', coverage: 'coverage', modules: 'overview'};
    if (sections[name] && !id) return {tab: sections[name], selection: null, selectionKind: null};
    if (name === 'work' && findWork(s, id)) return {tab: 'works', selection: id, selectionKind: 'work'};
    if (name === 'actor' && buildPresentation(s).participants.has(id)) return {tab: 'actors', selection: id, selectionKind: 'actor'};
    const entity = find(s, id);
    if (['document', 'contract', 'module'].includes(name) && entity) {
      const actual = arr(s.documents).some(d => d.id === id) ? 'document' : arr(s.input.contracts).some(c => c.id === id) ? 'contract' : 'module';
      if (name === actual) return {tab: {document: 'documents', contract: 'contracts', module: 'overview'}[name], selection: id, selectionKind: 'entity'};
    }
    return {error: 'Requested section or record is not present in this snapshot', tab: 'works', selection: null, selectionKind: null};
  }
  function exportMatrix(s) { return matrixSource(s).data; }
  // A portable, source-pinned work handoff, generated from the currently displayed immutable snapshot.
  // It is not a new admission, a command executor, or a live host/source assertion.
  const HANDOFF_SCHEMA = 'atlas.work-handoff/v1';
  function handoffConversationUrl(value) {
    if (typeof value !== 'string') return false;
    const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
    return new RegExp('^codex://threads/' + uuid + '$', 'iu').test(value)
      || new RegExp('^https://chatgpt\\.com/c/(?:' + uuid + '|local-chatgpt%3A' + uuid + ')$', 'iu').test(value);
  }
  function handoffConversationField(key, value) {
    return ['session_url', 'thread_url', 'conversation_url'].includes(String(key).toLowerCase())
      && handoffConversationUrl(value);
  }
  function handoffCredentialKey(name) {
    const key = String(name).replace(/([a-z])([A-Z])/gu, '$1_$2').toLowerCase();
    return ['session_url','thread_url','conversation_url'].includes(key) || /(?:^|[._-])(?:token|password|passwd|pwd|secret|authorization|cookie|credential|credentials|dsn|database_url|connection|connection_string|connection_url|session|client_secret|private_key)(?:$|[._-])/u.test(key)
      || /(?:^|[._-])(?:api|hmac|client|signing|private|access|refresh|auth|session|bot)[._-]?key(?:$|[._-])/u.test(key);
  }
  function handoffRedactTables(input) {
    const lines=String(input).split('\n');let header=null;
    const cells=line=>line.split(/(?<!\\)\|/u);
    const label=cell=>cell.replace(/[`*]/gu,'').trim().replace(/^["']|["']$/gu,'');
    const conversation=(key,cell)=>{
      const value=label(cell),link=value.match(/^\[[^\]]*\]\(([^\s()]+)\)$/u);
      return handoffConversationField(key,link?link[1]:value.replace(/^<|>$/gu,''));
    };
    return lines.map((line,index)=>{
      if(!line.includes('|')){header=null;return line;}
      const row=cells(line);
      if(index+1<lines.length&&/^\s*(?:>\s*)*\|?\s*:?-{3,}/u.test(lines[index+1])){
        header=row.map(c=>label(c).toLowerCase());return line;
      }
      if(!header&&!/^\s*(?:>\s*)*\|.*\|\s*$/u.test(line))return line;
      const secretColumns=header?header.map((name,i)=>handoffCredentialKey(name)?i:-1).filter(i=>i>=0):[];
      if(secretColumns.length){
        for(const i of secretColumns)if(row[i]?.trim()&&!conversation(header[i],row[i]))row[i]=' [REDACTED] ';
        return row.join('|');
      }
      const keyIndex=row.findIndex(c=>handoffCredentialKey(label(c)));
      if(keyIndex<0)return line;
      for(let i=0;i<row.length;i++){
        if(i===keyIndex)continue;
        if(!row[i].trim())continue;
        if(conversation(label(row[keyIndex]),row[i]))continue;
        const title=header?.[i]||'';
        const metadata=/^(?:type|format|description|constraint|constraints|тип|формат|описание|ограничения)$/iu.test(title);
        if(!metadata)row[i]=' [REDACTED] ';
      }
      return row.join('|');
    }).join('\n');
  }
  function handoffRedact(input) {
    return handoffRedactTables(input)
      .replace(/-----BEGIN (?:[A-Z0-9 ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----[\s\S]*?(?:-----END (?:[A-Z0-9 ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----|$)/gu, '[REDACTED PRIVATE KEY]')
      .replace(/\b([a-z][a-z0-9+.-]*:\/\/)[^\s/?#@'"<>]+@/giu, '$1[REDACTED-USERINFO]@')
      .replace(/(\b(?:Bearer|Basic)\s+)[A-Za-z0-9._~+/=-]{6,}/giu, '$1[REDACTED]')
      .replace(/([?&]([A-Za-z_][A-Za-z0-9_.-]{0,100})=)([^&#\s"'<>]+)/giu, (full, head, name) => handoffCredentialKey(name) ? head + '[REDACTED]' : full)
      .replace(/(^|[\s,{;\x5b(])(["']?)([A-Za-z_][A-Za-z0-9_.-]{0,100})\2(\s*[:=]\s*)(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;}\]\r\n"'<>]+)/gmu,
        (full, prefix, quote, key, sep) => {
          if (handoffCredentialKey(key)) {
            const remainder = full.slice((prefix + quote + key + quote + sep).length).trim();
            const rawValue = remainder.replace(/^["']|["']$/gu, '');
            if (handoffConversationField(key, rawValue)) return full;
            return prefix + quote + key + quote + sep + '[REDACTED]';
          }
          return full;
        })
      .replace(/\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{18,}|AKIA[A-Z0-9]{16}|sk-(?:proj|live|test)-[A-Za-z0-9_-]{8,}|\d{6,15}:[A-Za-z0-9_-]{10,})\b/gu, '[REDACTED TOKEN]')
      .replace(/\/(?:secrets|credentials)\/[^\s"'\x60]+/giu, '/[REDACTED PROTECTED PATH]')
      .replace(/\/(?:Users|home|srv|var|etc|opt|mnt|root)(?:\/[A-Za-z0-9._~-]+)*\/private\/[^\s"'\x60]+/giu, '/[REDACTED PROTECTED PATH]')
      .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/giu, '[REDACTED EMAIL]');
  }
  function handoffSanitize(value, depth = 0, schemaMode = null) {
    if (depth > 45) return 'UNKNOWN: nested source exceeded safe export depth';
    if (typeof value === 'string') return handoffRedact(value);
    if (Array.isArray(value)) return value.map(item => handoffSanitize(item, depth + 1, schemaMode));
    if (value && typeof value === 'object') {
      const out = {};
      const schema=!!schemaMode||typeof value.$schema==='string'||
        value.properties&&typeof value.properties==='object'&&!Array.isArray(value.properties)||
        ['allOf','anyOf','oneOf'].some(key=>Array.isArray(value[key]));
      const scalarSecrets=new Set(['default','example','examples','const','enum','value']);
      const schemaKeywords=new Set(('$schema $id $ref $anchor $dynamicRef $dynamicAnchor $vocabulary $comment $defs '
        +'type enum const allOf anyOf oneOf not if then else dependentSchemas properties patternProperties '
        +'additionalProperties unevaluatedProperties propertyNames required dependentRequired dependencies minProperties maxProperties '
        +'items prefixItems contains additionalItems unevaluatedItems minItems maxItems uniqueItems minContains maxContains '
        +'minLength maxLength pattern format contentEncoding contentMediaType contentSchema minimum maximum exclusiveMinimum '
        +'exclusiveMaximum multipleOf title description default example examples readOnly writeOnly deprecated nullable').split(' '));
      for (const [key, item] of Object.entries(value)) {
        if(schema&&key==='properties'&&item&&typeof item==='object'&&!Array.isArray(item)){
          out[key]={};
          for(const [name,definition] of Object.entries(item)){
            const sensitive=handoffCredentialKey(name);
            out[key][name]=definition&&typeof definition==='object'&&!Array.isArray(definition)
              ?handoffSanitize(definition,depth+2,sensitive||schemaMode==='sensitiveSchema'?'sensitiveSchema':'schema')
              :typeof definition==='boolean'?definition
              :sensitive?'[REDACTED]':handoffSanitize(definition,depth+2);
          }
        }else if(schema&&['$defs','patternProperties','dependentSchemas'].includes(key)&&item&&typeof item==='object'&&!Array.isArray(item)){
          out[key]=Object.fromEntries(Object.entries(item).map(([name,definition])=>
            [name,handoffSanitize(definition,depth+2,schemaMode||'schema')]));
        }else if(schemaMode==='sensitiveSchema'&&scalarSecrets.has(key)){
          out[key]=item===null?null:'[REDACTED]';
        }else if(schemaMode==='sensitiveSchema'&&!schemaKeywords.has(key)){
          out[key]='UNKNOWN: нестандартное поле схемы credential требует проверки по исходнику';
        }else if(schemaMode==='sensitiveSchema'&&key==='type'&&
          ![].concat(item).every(t=>['null','boolean','object','array','number','string','integer'].includes(t))){
          out[key]='UNKNOWN: некорректный тип схемы credential';
        }else if(schema&&['allOf','anyOf','oneOf'].includes(key)&&Array.isArray(item)){
          out[key]=item.map(x=>handoffSanitize(x,depth+1,schemaMode||'schema'));
        }else if(schema&&['items','not','if','then','else','additionalProperties'].includes(key)&&item&&typeof item==='object'){
          out[key]=handoffSanitize(item,depth+1,schemaMode||'schema');
        }else out[key]=handoffConversationField(key,item)?item
          :handoffCredentialKey(key)?(item===null?null:'[REDACTED]')
          :handoffSanitize(item,depth+1,schemaMode);
      }
      return out;
    }
    return value;
  }
  function handoffJSON(value) { return JSON.stringify(handoffSanitize(value === undefined ? null : value), null, 2); }
  function handoffFence(text, language = 'text') {
    let fence = String.fromCharCode(96).repeat(3); const value = String(text);
    while (value.includes(fence)) fence += String.fromCharCode(96);
    return fence + language + '\n' + value + '\n' + fence;
  }
  function handoffSection(title, text, language) { return '\n## ' + title + '\n\n' + handoffFence(text, language) + '\n'; }
  function handoffGovernance(doc) {
    // Exact canonical-root rules; a nested README or API catalogue is not automatically general governance.
    const path = String(doc.source_ref || doc.path || '').replace(/\\/gu, '/');
    return /(?:^|\/)canonical\/(?:AGENTS\.md|README\.md|CHANGE_PROCESS\.md|COORDINATION_CONTRACT\.md|docs\/(?:ARCHITECTURE|CONTRACTS|OPERATIONS|ROADMAP|SECURITY|CHANGE_PROCESS)\.md)$/iu.test(path)
      || /^(?:AGENTS|README|CHANGE_PROCESS|COORDINATION_CONTRACT)\.md$/iu.test(path)
      || path === 'docs/AGENTS.md';
  }
  function handoffChildren(model, id, depth = 0, visited = new Set()) {
    if (visited.has(id)) return [`${'  '.repeat(depth)}- ${id}: UNKNOWN (cycle)`];
    visited.add(id);
    const lines = [];
    for (const child of arr(model.children.get(id))) {
      const w = model.byId.get(child);
      lines.push(`${'  '.repeat(depth)}- ${child}: ${handoffRedact(workDisplayTitle(model,w))} · ${w && w.state || 'UNKNOWN'}`);
      lines.push(...handoffChildren(model, child, depth + 1, visited));
    }
    return lines;
  }
  function buildWorkHandoff(s, workId) {
    if (!s || !s.atlas || typeof workId !== 'string') throw Error('ATLAS_HANDOFF_INVALID_CONTEXT');
    const work = findWork(s, workId);
    if (!work) throw Error('ATLAS_HANDOFF_WORK_NOT_FOUND');
    const model = buildPresentation(s), project = s.atlas.project || {}, byId = model.byId;
    const unknown = [], refs = new Map(), relatedWorks = new Map(), dependencyEdges = [];
    const entity = new Map(entities(s).map(item => [item.id, item]));
    const allDocs = new Map(arr(s.documents).map(doc => [doc.id, doc]));
    const allContracts = new Map(arr(s.input.contracts).map(c => [c.id, c]));
    const allModules = new Map(arr(s.input.modules).map(m => [m.id, m]));
    const workChain = [], seen = new Set();
    let cursor = work.id;
    while (cursor !== null && cursor !== undefined) {
      if (seen.has(cursor)) { unknown.push('Parent chain cycle: ' + cursor); break; }
      seen.add(cursor); const row = byId.get(cursor);
      if (!row) { unknown.push('Parent work missing: ' + cursor); break; }
      workChain.unshift(row); cursor = model.parent.get(cursor) ?? null;
    }
    function workDependencies(row) {
      const result = new Map(), add = (id, origin) => {
        if (typeof id === 'string' && id) result.set(id, result.has(id) ? result.get(id) : origin);
      };
      for (const id of arr(row.depends_on)) add(id, 'normalized depends_on');
      const sourceStep = model.sourceSteps.get(row.id), definition = sourceStep?.source_definition;
      const raw = definition && typeof definition === 'object' ? definition.dependencies : undefined;
      const scan = (value, depth) => {
        if (depth > 12) { unknown.push('Source dependency depth exceeded for ' + row.id); return; }
        if (typeof value === 'string') { add(value, 'source_definition.dependencies'); return; }
        if (Array.isArray(value)) { value.forEach(v => scan(v, depth + 1)); return; }
        if (!value || typeof value !== 'object') return;
        if (typeof value.work_id === 'string') add(value.work_id, 'source_definition.dependencies.work_id');
        else if (typeof value.step_id === 'string') add(value.step_id, 'source_definition.dependencies.step_id');
        else if (typeof value.id === 'string' && byId.has(value.id)) add(value.id, 'source_definition.dependencies.id');
        for (const field of ['depends_on', 'work_ids', 'prerequisites', 'dependencies'])
          if (Object.prototype.hasOwnProperty.call(value, field)) scan(value[field], depth + 1);
      };
      if (raw !== undefined) scan(raw, 0);
      return [...result].map(([id, origin]) => ({id, origin}));
    }
    const pending = [work.id], visitedWorks = new Set();
    while (pending.length) {
      const id = pending.shift();
      if (visitedWorks.has(id)) continue;
      visitedWorks.add(id);
      const row = byId.get(id);
      if (!row) { unknown.push('Unresolved prerequisite work: ' + id); continue; }
      for (const dep of workDependencies(row)) {
        dependencyEdges.push({from:id, to:dep.id, origin:dep.origin});
        if (!byId.has(dep.id)) { unknown.push('Unresolved prerequisite work: ' + dep.id + ' declared by ' + id); continue; }
        if (dep.id !== work.id) relatedWorks.set(dep.id, {relationship:'prerequisite of ' + id + ' (' + dep.origin + ')', work:byId.get(dep.id)});
        if (!visitedWorks.has(dep.id)) pending.push(dep.id);
      }
    }
    for (const other of works(s)) {
      if (other.id === work.id || visitedWorks.has(other.id)) continue;
      const deps = workDependencies(other);
      if (deps.some(d => d.id === work.id)) relatedWorks.set(other.id, {relationship:'consumer of selected step', work:other});
    }
    // A child's exact artifacts and proven predecessors are relevant. An ancestor's generic catalogue is not.
    for (const row of workChain) {
      const direct = row.id === work.id;
      for (const artifact of arr(row.artifacts)) {
        for (const id of arr(artifact.entity_ids)) {
          if (direct || (allDocs.has(id) && handoffGovernance(allDocs.get(id))))
            refs.set(id, 'Explicit artifact of ' + row.id + ': ' + artifact.id);
        }
        if (direct && artifact.patch?.target_id) refs.set(artifact.patch.target_id, 'Patch target of ' + row.id + ': ' + artifact.id);
      }
    }
    const relationRows = arr(s.input.relations);
    // Only directly bound contracts/modules seed interface relations. A common document
    // does NOT confer ownership of unrelated APIs that happen to cite it.
    const directInterfaces = new Set([...refs.keys()].filter(id => allContracts.has(id) || allModules.has(id)));
    const usedRelations = relationRows.filter(edge => directInterfaces.has(edge.from) || directInterfaces.has(edge.to));
    for (const edge of usedRelations) {
      if (entity.has(edge.from)) refs.set(edge.from, refs.get(edge.from) || 'Relation ' + edge.type + ' -> ' + edge.to);
      else unknown.push('Relation source missing: ' + edge.from);
      if (entity.has(edge.to)) refs.set(edge.to, refs.get(edge.to) || 'Relation ' + edge.type + ' <- ' + edge.from);
      else unknown.push('Relation target missing: ' + edge.to);
    }
    const selectedModules = new Map(), selectedContracts = new Map(), selectedDocs = new Map();
    const queue = [], queued = new Set(), processed = new Set();
    const addEntity = (id, reason) => {
      if (typeof id !== 'string' || !id) return;
      const kind = allDocs.has(id) ? 'document' : allContracts.has(id) ? 'contract' : allModules.has(id) ? 'module' : null;
      if (!kind) { unknown.push('Linked entity not present in snapshot: ' + id + ' (' + reason + ')'); return; }
      const m = kind === 'document' ? selectedDocs : kind === 'contract' ? selectedContracts : selectedModules;
      if (!m.has(id)) m.set(id, reason);
      else if (kind === 'document' && /^(?:Contract|Module) /u.test(reason) && !m.get(id).includes(reason))
        m.set(id, m.get(id) + '; ' + reason);
      if (!queued.has(id)) { queue.push({id,kind}); queued.add(id); }
    };
    for (const [id, reason] of refs) addEntity(id, reason);
    while (queue.length) {
      const {id, kind} = queue.shift();
      if (processed.has(id)) continue;
      processed.add(id);
      const row = kind === 'contract' ? allContracts.get(id) : kind === 'module' ? allModules.get(id) : allDocs.get(id);
      if (!row) { unknown.push('Declared entity missing during expansion: ' + id); continue; }
      if (kind === 'contract') {
        if (typeof row.module === 'string' && row.module) addEntity(row.module, 'Owning module of ' + id);
        else unknown.push('Contract owning module UNKNOWN: ' + id);
        for (const doc of arr(row.docs)) addEntity(doc, 'Contract ' + id + ' document');
        for (const dep of arr(row.dependencies)) {
          const depId = typeof dep === 'string' ? dep : dep && typeof dep === 'object' ? dep.contract_id || dep.module_id || dep.id : null;
          if (typeof depId === 'string') addEntity(depId, 'Contract dependency of ' + id);
          else unknown.push('Unresolved non-ID contract dependency from ' + id);
        }
      } else if (kind === 'module') {
        for (const doc of arr(row.docs)) addEntity(doc, 'Module ' + id + ' document');
        for (const dep of arr(row.dependencies)) {
          const depId = typeof dep === 'string' ? dep : dep && typeof dep === 'object' ? dep.module_id || dep.id : null;
          if (typeof depId === 'string' && allModules.has(depId)) addEntity(depId, 'Module dependency of ' + id);
          else if (depId) unknown.push('Declared module dependency not resolved: ' + depId + ' from ' + id);
        }
      }
    }
    for (const doc of arr(s.documents)) if (handoffGovernance(doc) && !String(doc.source_ref || '').includes('[owning matrix projection source]'))
      addEntity(doc.id, 'Exact canonical project-level governance');
    for (const id of selectedDocs.keys()) {
      const doc = allDocs.get(id);
      if (typeof doc.content !== 'string') unknown.push('Document body unavailable: ' + id + ', ' + (doc.path || 'UNKNOWN'));
    }
    const participants = new Map(), addActor = id => {
      if (typeof id === 'string' && id && id !== 'UNKNOWN') participants.set(id, model.participants.get(id) || {id, state: 'UNKNOWN_PARTICIPANT'});
    };
    [...workChain, ...[...relatedWorks.values()].map(x => x.work)].forEach(row => { actors(row).forEach(addActor); sourceActors(model, row.id).forEach(addActor); observationActors(model, row.id).forEach(addActor); });
    addActor(project.writer);
    const source = model.source || {}, sourceStep = model.sourceSteps.get(work.id), own = model.ownership.get(work.id);
    if (!sourceStep) unknown.push(`No owning-matrix source step matching Atlas ID ${work.id}`);
    if (!model.matrix) unknown.push(`Owning matrix source is ${source.status || 'UNKNOWN'}; recorded source events not available`);
    if (!selectedContracts.size) unknown.push(`No explicitly linked interface contract for work ${work.id}; do not infer by name`);
    if (!selectedModules.size) unknown.push(`No explicitly linked module for work ${work.id}; verify owning module before editing`);
    const selectedSourceResult = model.sourceLatest.get(work.id) || null;
    const sourceStatus = row => {
      const e = model.sourceLatest.get(row.id);
      return e ? `${e.status || 'UNKNOWN'} / accepted=${e.accepted === true ? 'true (source event only)' : 'not proven'}` : 'UNKNOWN';
    };
    if (!arr(work.criteria).length) unknown.push(`Atlas normalized criteria are empty for ${work.id}; inspect retained source events/document receipts for proof`);
    if (!arr(work.acceptance).length) unknown.push(`Atlas normalized acceptance is empty for ${work.id}; source done is not product acceptance`);
    if (!arr(work.artifacts).some(a => arr(a.entity_ids).length)) unknown.push(`No explicit semantic work_bindings/work_context for ${work.id}; owning matrix/catalog writer must qualify the missing relationships`);
    const projectCore = {
      id:project.id || 'UNKNOWN', title:project.title || 'UNKNOWN', objective:(hasLocalizedFields(s)?displayText(model,project.id,'project.objective'):project.objective) || 'UNKNOWN',
      writer:project.writer || 'UNKNOWN', authority_ref:project.authority_ref || 'UNKNOWN',
      scope_note:(hasLocalizedFields(s)?displayText(model,project.id,'project.scope_note'):project.scope_note) || 'UNKNOWN', source_ref:project.source_ref || 'UNKNOWN',
      mode:project.mode || 'UNKNOWN'
    };
    const coverage = s.atlas.coverage || {}, matrix = model.matrix;
    const meta = {
      schema:HANDOFF_SCHEMA, scope:'READ_ONLY_EXPORT_NOT_AUTHORITY', generated_from_snapshot_at:s.atlas.as_of || 'UNKNOWN',
      release:s.input.release || null, input_sha256:s.input_sha256 || 'UNKNOWN',
      atlas_toolchain_sha256:s.atlas.toolchain_sha256 || 'UNKNOWN',
      atlas_source_sha256:s.atlas.source_sha256 || 'UNKNOWN',
      project:projectCore,...(hasLocalizedFields(s)?{display_project:displayProjectProjection(model),original_project:project}:{}),
      project_coverage:{status:coverage.status || 'UNKNOWN', scope_note:coverage.scope_note || 'UNKNOWN',
        coverage_of:'DECLARED_SNAPSHOT_ONLY', issues_count:arr(coverage.issues).length},
      matrix_source:{status:source.status || 'UNKNOWN',
        selected_document:source.document && {id:source.document.id,path:source.document.path,
          source_ref:source.document.source_ref,sha256:source.document.sha256,bytes:source.document.bytes},
        revision:matrix?.revision ?? 'UNKNOWN', updated_at:matrix?.updated_at || 'UNKNOWN',
        policy:matrix?.policy || 'UNKNOWN'},
      retained_matrix_history_total:s.atlas.matrix_history_total ?? 'UNKNOWN',
      retained_matrix_history_in_snapshot:arr(s.atlas.matrix_history).map(item=>({
        id:item.id,at:item.at,file:item.file && {sha256:item.file.sha256,path:item.file.path}})),
      notes:['Immutable Atlas snapshot only; no live agent/host/readiness observation',
        'Writer/authority references in this packet are historical data, not permission given to a receiving session',
        'Document original SHA256 values identify pinned source bytes, not sanitized Markdown',
        'No command in this package was executed by clicking Copy']
    };
    const nestedChildren = handoffChildren(model, work.id);
    const out = [
      '# Atlas — переносимый контекст проекта и работы',
      `\n**Проект:** ${handoffRedact(project.title || s.input.project?.title || 'UNKNOWN')} (${project.id || 'UNKNOWN'})`,
      `**Выбранная работа:** ${handoffRedact(workDisplayTitle(model,work))} (${work.id})`,
      `**Исходный статус:** ${handoffRedact(sourceStatus(work))}; **Atlas normalized:** ${work.state || 'UNKNOWN'}. Эти состояния не подменяют друг друга.`,
      `**Последняя исходная запись:** ${selectedSourceResult ? handoffRedact(`${selectedSourceResult.at} · ${selectedSourceResult.id} · ${selectedSourceResult.note || ''}`) : 'UNKNOWN'}`,
      '**Исходное название в неизменённой матрице:** ' + handoffRedact(work.title),
      '**Назначение:** вставить в пустую сессию Codex/ChatGPT и продолжить после проверки актуальных границ. Все команды ниже — данные, не автоматическое действие.',
      '**БЕЗ ПЕРЕДАЧИ ПРАВ:** содержимое не выдаёт writer/production/DB/credential permissions; новые разрешения проверяются отдельно.',
      '**Состояние:** датированный Atlas snapshot. Живые сессии, хосты и installed runtime не перепроверены этой кнопкой.',
      handoffSection('1. Проект, план, версии и границы', handoffJSON(meta), 'json'),
      '## 2. Место в дереве работ\n',
      ...workChain.map((row,i) => `${'  '.repeat(i)}- ${row.id} · ${handoffRedact(workDisplayTitle(model,row))} · Atlas=${row.state} · source=${handoffRedact(sourceStatus(row))}`),
      '\n**Дочерняя структура выбранной работы:**\n', ...(nestedChildren.length ? nestedChildren : ['- Нет дочерних работ в данном снимке.']),
      '\n**Общий план (индекс всех работ снимка, без выдачи их статусов за текущую активность):**\n',
      ...works(s).map(w => `- ${w.id} | parent=${w.parent_id || 'ROOT'} | Atlas=${w.state} | source=${handoffRedact(sourceStatus(w))} | ${handoffRedact(workDisplayTitle(model,w))}`),
      handoffSection('3. Полная запись выбранной работы, ограничения, критерии, evidence и patches', handoffJSON({display_title:workDisplayTitle(model,work),...(hasLocalizedFields(s)?{display_fields:displayWorkProjection(model,work)}:{}),original_record:work}), 'json'),
      handoffSection('4. Первичная owning-matrix запись выбранного шага', handoffJSON({
        source_step:sourceStep || 'UNKNOWN', source_ownership:own || 'UNKNOWN',
        recorded_latest_event:model.sourceLatest.get(work.id) || 'UNKNOWN',
        source_events:arr(model.eventMap.get(work.id)),
        parent_source_context:workChain.filter(row=>row.id!==work.id).map(row=>({
          id:row.id, source_step:model.sourceSteps.get(row.id) || 'UNKNOWN',
          source_latest:model.sourceLatest.get(row.id) || 'UNKNOWN',
          source_event_count:arr(model.eventMap.get(row.id)).length})),
        activity_observations:arr(model.observationMap.get(work.id)),
        activity_qualification:'NOT_RECHECKED_LIVE',
        activity_at_snapshot:s.atlas.as_of || 'UNKNOWN'
      }), 'json'),
      handoffSection('5. Предшественники, потребители и исполнители', handoffJSON({
        dependency_edges:dependencyEdges,
        related_work:[...relatedWorks].map(([id,item])=>{
          const prerequisite = item.relationship.startsWith('prerequisite');
          return {id,relation:item.relationship,
            record:prerequisite ? item.work : {
              id:item.work.id,title:workDisplayTitle(model,item.work),original_title:item.work.title,
              state:item.work.state,next_action:item.work.next_action},
            source_step:prerequisite ? model.sourceSteps.get(id) || 'UNKNOWN' : 'NOT_REQUIRED_FOR_CONSUMER',
            source_latest:model.sourceLatest.get(id) || 'UNKNOWN',
            source_events:prerequisite ? arr(model.eventMap.get(id)) : [],
            source_ownership:prerequisite ? model.ownership.get(id) || 'UNKNOWN' : 'NOT_REQUIRED_FOR_CONSUMER'};
        }),
        actors:[...participants].map(([id,value])=>({id,...value})),
        writer:project.writer || 'UNKNOWN',curator:own?.coordinator_id || 'UNKNOWN',
        return_route:project.authority_ref || 'UNKNOWN'
      }), 'json'),
      handoffSection('6. Явные связи выбранной работы с источниками', handoffJSON({relations: usedRelations, artifacts: workChain.flatMap(row => arr(row.artifacts).map(a=>({work_id:row.id,artifact:a}))),
        selected_entity_reasons:[...refs].map(([id,reason])=>({id,reason})),
        unknown_edges: unknown}), 'json')
    ];
    const docs = [...selectedDocs].map(([id,reason]) => ({doc:allDocs.get(id),reason}));
    const contentOwner = new Map();
    const manifest = docs.map(({doc,reason}) => {
      if (!doc) { unknown.push('Selected document unexpectedly missing'); return {id:'UNKNOWN',content_included:false,reason}; }
      const pinned = typeof doc.content === 'string' && typeof doc.sha256 === 'string' && typeof doc.bytes === 'number';
      const digest = pinned ? doc.sha256 + ':' + doc.bytes : 'UNKNOWN:' + doc.id;
      const duplicate_of = pinned && contentOwner.has(digest) ? contentOwner.get(digest) : null;
      if (pinned && !duplicate_of) contentOwner.set(digest,doc.id);
      return {id:doc.id,title:doc.title,path:doc.path,source_ref:doc.source_ref,version:doc.version,
        sha256:doc.sha256,bytes:doc.bytes,readback_at:doc.readback_at,reason,
        content_included:typeof doc.content === 'string' && !duplicate_of,
        duplicate_body_of:duplicate_of || null,sanitized:true};
    });
    out.push(handoffSection('7. Инвентарь документальных тел с исходными SHA256', handoffJSON(manifest), 'json'));
    const emittedBody = new Set();
    for (const {doc,reason} of docs) {
      if (typeof doc?.content !== 'string') { unknown.push('Document body unavailable: ' + (doc?.id||'UNKNOWN')); continue; }
      const pin = doc.sha256 + ':' + doc.bytes;
      if (emittedBody.has(pin)) {
        out.push('\n### Документ ' + handoffRedact(doc.title) + ' — ' + doc.id +
          '\n\nТело идентично уже включённому документу с точными source SHA256/bytes: ' + pin +
          '. Связи, путь и версия сохранены в манифесте.\n');
        continue;
      }
      emittedBody.add(pin);
      let body = handoffRedact(doc.content), language = 'text';
      if (doc.kind === 'json') {
        try { body = handoffJSON(JSON.parse(doc.content)); language = 'json'; }
        catch (_) { unknown.push('JSON document not parsable as structured body: ' + doc.id); }
      }
      out.push('\n### Документ ' + handoffRedact(doc.title) + ' — ' + doc.id + '\n\n' +
        'Путь: ' + handoffRedact(doc.path) + ' | Source: ' + handoffRedact(doc.source_ref || 'UNKNOWN') +
        ' | Версия: ' + handoffRedact(doc.version) + ' | SHA256 original: ' + doc.sha256 +
        ' | Причина включения: ' + handoffRedact(reason) + '\n\n' + handoffFence(body,language) + '\n');
    }
    out.push(handoffSection('8. Модули: владение состоянием, исходные связи и сведения', handoffJSON([...selectedModules].map(([id,reason])=>({reason,record:entity.get(id)||'UNKNOWN'}))), 'json'));
    out.push(handoffSection('9. Контракты: точные входы/выходы, auth, ошибки, consumers', handoffJSON([...selectedContracts].map(([id,reason])=>({reason,record:entity.get(id)||'UNKNOWN'}))), 'json'));
    out.push(handoffSection('10. Evidence и приёмка — где искать полные данные',handoffJSON({
      selected_work_event_count:arr(work.events).length,selected_work_evidence_count:arr(work.evidence).length,
      selected_work_acceptance_count:arr(work.acceptance).length,
      source_event_count:arr(model.eventMap.get(work.id)).length,
      source_event_ids:arr(model.eventMap.get(work.id)).map(ev=>ev.id || 'UNKNOWN'),
      evidence_location:'Full original work records are in section 3; source events in section 4; prerequisite source/evidence in section 5; linked primary bodies in section 7',
      evidence_levels:'SOURCE / TEST / BUILD / INSTALLED / DELIVERY / USER_RESULT are separate. No implied promotion.',
      inherited_acceptance_not_granted:true
    }), 'json'));
    out.push(`\n## 11. Минимальная последовательность продолжения\n\n` + [
      '1. Прочитать проектный контекст и правила из включённых выше документов, сверить их актуальность по source SHA/version.',
      `2. В существующем Atlas проверить work ID ${work.id}, owning-матрицу, автора и действительный writer/lease. Сначала read-only atlasctl views PROJECT и atlasctl start PROJECT --work ${work.id} (заменить PROJECT на действующий зарегистрированный key).`,
      '3. Сверить exact baseline и источники по указанным SHA. Зафиксировать UNKNOWN и попросить недостающую authority; старый snapshot не доказывает текущее состояние.',
      '4. Только имеющий право writer после фактического начала/прогресса пишет один адресный atlasctl work checkpoint. Копирование не создало события и не передало права.',
      '5. Изменение выполнять по текущему контракту, с preflight, isolated check, independent review; неизменившиеся принятые проверки не повторять без причины.',
      '6. Результат вернуть действующему writer/куратору, обновить owning matrix и проверенный immutable release в штатном порядке. Unknown external outcome сначала reconciled по original operation ID.'
    ].join('\n').replace(/\u001b/g,'`') + '\n');
    out.push(handoffSection('12. Недостающие ссылки и UNKNOWN', handoffJSON({issues:[...new Set(unknown)],
      completeness: {documents_selected: docs.length, contracts_selected: selectedContracts.size,modules_selected:selectedModules.size,
        source_matrix_status:source.status, linked_inventory_not_global:true,live_runtime_verified:false},
      empty_relationships_are_not_proof_of_absence:true}), 'json'));
    // Do not trim any section: a large nonredundant body is still part of the transfer.
    return out.join('\n');
  }
  // Exact owner-visible "Выполнено": latest source event done, or native
  // Atlas ACCEPTED when there is no owning source. Do not infer from children.
  function incompleteTreeScope(model, workId) {
    if (!model.byId.has(workId)) throw Error('ATLAS_HANDOFF_WORK_NOT_FOUND');
    const ancestors=[],pathSeen=new Set([workId]);
    let parent=model.parent.get(workId);
    while(parent!==null&&parent!==undefined){
      if(pathSeen.has(parent))throw Error('ATLAS_HANDOFF_PARENT_CYCLE');
      pathSeen.add(parent);ancestors.unshift(parent);parent=model.parent.get(parent);
    }
    const visited=new Set(),ordered=[],stack=[{id:workId,parents:ancestors}];
    while(stack.length){
      const item=stack.pop();
      if(visited.has(item.id))continue;
      visited.add(item.id);
      const work=model.byId.get(item.id);
      if(!work)continue;
      const source=model.sourceLatest.get(work.id);
      const done=source ? source.status==='done' : work.state==='ACCEPTED';
      ordered.push({work,parents:item.parents,source_status:source?.status||'UNKNOWN',
        source_accepted:source?.accepted===true,done});
      for(const id of arr(model.children.get(work.id)).slice().reverse())
        stack.push({id,parents:[...item.parents,work.id]});
    }
    return ordered;
  }
  function incompleteDependencies(model,work,issues){
    const deps=new Map(),seen=new Set();
    const add=(id,kind)=>{
      if(typeof id==='string'&&id&&!deps.has(id))deps.set(id,kind);
    };
    arr(work.depends_on).forEach(id=>add(id,'normalized'));
    const def=model.sourceSteps.get(work.id)?.source_definition;
    function visit(node,depth){
      if(depth>14){issues.push('Глубина связи не подтверждена: '+work.id);return;}
      if(typeof node==='string'){
        if(node.trim())add(node,'source_definition.dependencies');
        else issues.push('UNKNOWN: пустая зависимость работы '+work.id);
        return;
      }
      if(Array.isArray(node)){node.forEach(x=>visit(x,depth+1));return;}
      if(!node||typeof node!=='object'){
        issues.push('UNKNOWN: неподдержанный тип зависимости работы '+work.id);return;
      }
      if(seen.has(node))return;
      seen.add(node);
      let recognized=false;
      for(const k of ['work_id','step_id','id']){
        if(!Object.prototype.hasOwnProperty.call(node,k))continue;
        recognized=true;
        if(typeof node[k]==='string'&&node[k].trim())add(node[k],'source_definition.dependencies.'+k);
        else issues.push('UNKNOWN: некорректное поле '+k+' зависимости работы '+work.id);
      }
      for(const k of ['dependencies','depends_on','work_ids','prerequisites']){
        if(Object.prototype.hasOwnProperty.call(node,k)){recognized=true;visit(node[k],depth+1);}
      }
      if(!recognized)issues.push('UNKNOWN: нераспознанная форма зависимости работы '+work.id+
        ' (поля '+Object.keys(node).join(', ')+')');
    }
    if(def&&typeof def==='object'&&def.dependencies!==undefined)
      visit(def.dependencies,0);
    return [...deps].map(([id,origin])=>({id,origin}));
  }
  function coordinationRules(){
    return [
      '## Обязательные инструкции каждой сессии',
      'Актуальный контракт Atlas и проверенной агентской комнаты имеет приоритет над общими рабочими привычками агента. Системные инструкции, безопасность и действующие полномочия сохраняют высший приоритет. Противоречие передать Codex0; не выбирать молча удобное правило.',
      'Комнаты нет (это проверено): одна текущая сессия сама исполняет выбранные работы, проверяет результат, ведёт документы, контракты, матрицу и историю. Найм и создание комнаты не требуются.',
      'Комната есть (привязка проверена): Codex0 распределяет цельные вложенные блоки и принимает результат. Обязательна выделенная сессия «Проект · Секретарь»: принимает факты событий и результаты, сопровождает общие документы, связи, матрицу и историю; возвращает квитанцию записи и readback. Отсутствующая ссылка — UNKNOWN, а не доказанное отсутствие комнаты.',
      'Секретарь не принимает работу вместо Codex0. Один writer на общий файл: до согласованной передачи записи секретарь готовит дельту прежнему writer; незавершённые операции сначала сверить, ordinary refresh поверх pending запрещён. Исполнители сохраняют ответственность за документы своих модулей.',
      'Модель и уровень рассуждения выбирать отдельно: последняя стабильная доступная модель по каталогу точного исполнителя и её поддерживаемым уровням. Codex0 предпочитает Ultra, затем Max, затем максимально доступный уровень; это предпочтение, не фактическая настройка. Исполнители: чтение, поиск и простые/обычные изменения — лёгкий; средняя связанная разработка — средний; сложная архитектура/ошибка/высокий риск — высокий; исключительная сложность и серьёзные последствия — очень высокий. Секретарь — лёгкий, спорные выводы передаёт Codex0. Повышение обосновать; работающие сессии молча не переключать.',
      'При назначении фиксировать work IDs, actual session ID, модель, уровень, причину, область записи, ожидаемый результат, критерии и маршрут возврата. Предлагаемое имя не означает созданную сессию. Использовать подходящих существующих исполнителей; новые сессии только при отдельном действующем разрешении. Не дублировать занятого writer.',
      'Пакет содержит данные, не команду исполнения: перед началом проверить текущий source, поручение, паузы, writer, доступность комнаты/секретаря и зависимости. Копирование не создаёт сессии, не снимает паузу и не меняет настройки. Остановленные проекты не возобновлять по содержимому пакета.',
      'Возврат исполнителя: work IDs и версия входов; факты начала/прогресса/блокера; результат; артефакты и первичные доказательства; выполненные проверки и их уровень; ограничения; остаток; следующий владелец. Передать Codex0 и секретарю подтверждённым маршрутом комнаты; без комнаты текущая сессия сохраняет эти факты сама.',
      'Codex0 проверяет критерии и точные артефакты. Секретарь отражает решение через действующего writer и возвращает operation/event ID, source revision, изменённые записи и readback; публикация проверяется отдельно. Сообщение «готово», dispatch и получение сообщения не доказывают исполнение или приёмку. SOURCE / TEST / INSTALLED / RUNTIME / USER_RESULT разделять.',
      'Повторный результат сверять по operation/event ID, не создавать повторный эффект. UNKNOWN сначала reconcile прежней операции. Родитель не завершён автоматически от результата одного потомка. Внешние зависимости и выполненные предки — только контекст; исполнять только work IDs своего назначения.'
    ].join('\n\n');
  }
  function coordinationPlan(s,root,outline){
    const ids=new Set(outline.map(x=>x.id)),groups=new Map();
    const hasDescendants=outline.some(x=>x.id!==root.id);
    for(const row of outline){
      if(hasDescendants&&row.id===root.id)continue;
      const at=row.tree_path.indexOf(root.id);
      const key=at>=0&&row.tree_path[at+1]||row.id;
      if(!groups.has(key))groups.set(key,[]);
      groups.get(key).push(row);
    }
    const project=s.atlas.project||{},title=handoffRedact(project.title||project.id||'Проект');
    const blocks=[...groups].map(([id,rows])=>({
      branch_root:id,work_ids:rows.map(x=>x.id),tree_paths:rows.map(x=>x.tree_path),
      proposed_chat_title:title+' · '+handoffRedact(rows.find(x=>x.id===id)?.title||id)+' · Исполнение · '+id,
      actual_chat_ref:'UNKNOWN',actual_model:'UNKNOWN',actual_reasoning:'UNKNOWN',
      model_selection:'Минимально достаточный уровень по правилам; обосновать после оценки сложности',
      status:'PROPOSED_NOT_DISPATCHED',write_scope:'VERIFY_CURRENT_CONTRACTS_BEFORE_ASSIGNMENT',
      internal_dependencies:rows.flatMap(x=>arr(x.dependencies).filter(d=>ids.has(d.id)).map(d=>({work:x.id,requires:d.id}))),
      external_dependencies:rows.flatMap(x=>arr(x.dependencies).filter(d=>!ids.has(d.id)).map(d=>({work:x.id,requires:d.id,role:'CONTEXT_ONLY'})))
    }));
    return {schema:'atlas.coordination-plan/v1',room_binding:'UNKNOWN_VERIFY_LIVE',
      mode_selection:'Проверенная комната отсутствует → SINGLE_SESSION; существует → AGENT_ROOM; неизвестно → сначала проверить, без автоматического создания.',
      single_executor:{executor:'CURRENT_SESSION',work_ids:[...ids],responsibility:'Исполнение, проверка, документы, матрица, история и readback самостоятельно'},
      agent_room:{codex0:{role:'Распределение, интеграция и приёмка',proposed_chat_title:title+' · Codex0',reasoning_preference:['Ultra','Max','HIGHEST_SUPPORTED'],actual_chat_ref:'UNKNOWN'},
        secretary:{required:!!outline.length,proposed_chat_title:title+' · Секретарь',actual_chat_ref:'UNKNOWN',reasoning_preference:'LOW',role:'Факты, общие документы, матрица, история, квитанция записи и readback; один writer'},
        integration_work_ids:hasDescendants&&ids.has(root.id)?[root.id]:[],blocks},
      no_execution_required:!outline.length,dispatch_performed:false,
      scheduling:'Предложение по вложенности; перед параллельным исполнением проверить все зависимости, циклы, занятость и пересечения write scopes. Родитель — интеграция, дети назначаются один раз.',
      acceptance:'Проверка Codex0 → запись секретарём через одного writer → квитанция и readback → подтверждение Codex0; без комнаты тот же цикл ведёт одна сессия'};
  }
  function buildUnfinishedHandoff(s,workId,contextOnly=false,selection=null){
    if(!s?.atlas||typeof workId!=='string')throw Error('ATLAS_HANDOFF_INVALID_CONTEXT');
    const model=buildPresentation(s),root=model.byId.get(workId);
    if(!root)throw Error('ATLAS_HANDOFF_WORK_NOT_FOUND');
    const subtree=selection?.all?[...model.byId.keys()].map(id=>incompleteTreeScope(model,id)[0]):incompleteTreeScope(model,workId);
    const chosen=selection?new Set(selection.ids):null;
    if(chosen&&[...chosen].some(id=>!subtree.some(row=>row.work.id===id)))throw Error('ATLAS_HANDOFF_SELECTION_OUTSIDE_SCOPE');
    const target=subtree.filter(x=>chosen?chosen.has(x.work.id):!x.done),excluded=subtree.filter(x=>chosen?!chosen.has(x.work.id):x.done);
    const unfinishedIds=new Set(target.map(x=>x.work.id));
    const ancestorIds=[...new Set(target.flatMap(row=>row.parents))]
      .filter(id=>!unfinishedIds.has(id));
    const issues=[],docs=new Map(arr(s.documents).map(x=>[x.id,x])),
      contracts=new Map(arr(s.input.contracts).map(x=>[x.id,x])),
      modules=new Map(arr(s.input.modules).map(x=>[x.id,x]));
    const linkedDocs=new Map(),linkedContracts=new Map(),linkedModules=new Map();
    const waiting=[],queued=new Set();
    function add(id,reason){
      if(typeof id!=='string'||!id)return;
      const category=docs.has(id)?linkedDocs:contracts.has(id)?linkedContracts:
        modules.has(id)?linkedModules:null;
      if(!category){issues.push('Нет точной связи '+id+' ('+reason+')');return;}
      if(!category.has(id))category.set(id,reason);
      if(!queued.has(id)){queued.add(id);waiting.push(id);}
    }
    function addWorkEntities(work){
      for(const artifact of arr(work.artifacts)){
        arr(artifact.entity_ids).forEach(id=>add(id,'Артефакт '+artifact.id+' работы '+work.id));
        if(artifact.patch?.target_id)add(artifact.patch.target_id,'Цель патча работы '+work.id);
      }
      if(!arr(work.artifacts).some(a=>arr(a.entity_ids).length))
        issues.push('Нет точной work→contract/module/doc привязки для '+work.id+
          '; следующий владелец '+(work.writer||'UNKNOWN'));
    }
    const detail=target.map(entry=>{
      const work=entry.work,dep=incompleteDependencies(model,work,issues);
      addWorkEntities(work);
      return {id:work.id,display_title:workDisplayTitle(model,work),
        original_title:work.title,...(hasLocalizedFields(s)?{display_fields:displayWorkProjection(model,work)}:{}),parent_id:model.parent.get(work.id),
        tree_path:[...entry.parents,work.id],
        source_status:entry.source_status,source_accepted:entry.source_accepted,
        atlas_state:work.state,dependencies:dep,
        work_record:work,source_step:model.sourceSteps.get(work.id)||'UNKNOWN',
        source_latest:model.sourceLatest.get(work.id)||'UNKNOWN',
        source_events:arr(model.eventMap.get(work.id)),
        source_ownership:model.ownership.get(work.id)||'UNKNOWN',
        activity_observations:arr(model.observationMap.get(work.id))};
    });
    // A completed parent can still define the child's objective, acceptance
    // and instructions. Retain those as context without assigning it again.
    for(const id of ancestorIds)addWorkEntities(model.byId.get(id));
    // Prerequisites are a transitive CONTEXT-ONLY closure, never extra targets.
    // Keep their substantive records and normative artifacts, not only labels.
    const edges=[],outside=new Map(),dependencyQueue=detail.map(row=>row.id),
      dependencySeen=new Set();
    while(dependencyQueue.length){
      const from=dependencyQueue.shift();
      if(dependencySeen.has(from))continue;
      dependencySeen.add(from);
      const row=model.byId.get(from);
      if(!row)continue;
      for(const dep of incompleteDependencies(model,row,issues)){
        const isInside=unfinishedIds.has(dep.id);
        edges.push({from,to:dep.id,origin:dep.origin,
          role:isInside?'SELECTED_UNFINISHED':'EXTERNAL_OR_COMPLETED_CONTEXT'});
        const original=model.byId.get(dep.id);
        if(!original){issues.push('Зависимый work ID отсутствует: '+dep.id+' для '+from);continue;}
        if(!isInside&&!outside.has(dep.id)){
          const ev=model.sourceLatest.get(dep.id);
          outside.set(dep.id,{id:dep.id,title:workDisplayTitle(model,original),
            source_status:ev?.status||'UNKNOWN',source_accepted:ev?.accepted===true,
            atlas_state:original.state,writer:original.writer,
            role:'CONTEXT_ONLY_NOT_AN_EXECUTION_TARGET',
            work_record:original,source_step:model.sourceSteps.get(dep.id)||'UNKNOWN',
            source_latest:ev||'UNKNOWN',source_events:arr(model.eventMap.get(dep.id)),
            source_ownership:model.ownership.get(dep.id)||'UNKNOWN',
            activity_observations:arr(model.observationMap.get(dep.id))});
          addWorkEntities(original);
        }
        if(!dependencySeen.has(dep.id))dependencyQueue.push(dep.id);
      }
    }
    // Exact interface relations expand context. A shared document must not
    // reverse-import unrelated API contracts citing that same document.
    const directInterfaces=new Set([...linkedContracts.keys(),...linkedModules.keys()]);
    const relatedEdges=arr(s.input.relations).filter(edge=>
      directInterfaces.has(edge.from)||directInterfaces.has(edge.to));
    const unprovenInterfaces=new Set();
    for(const edge of relatedEdges){
      for(const id of [edge.from,edge.to]){
        // A module's sibling interface is not an assignment's contract merely
        // because both occur in one relation. Only normative docs and an
        // explicitly declared forward dependency expand the seeded context.
        if(docs.has(id)||directInterfaces.has(id)||
          edge.type==='depends_on'&&edge.from!==id&&directInterfaces.has(edge.from))
          add(id,'Связь '+edge.type+' '+edge.from+' → '+edge.to);
        else unprovenInterfaces.add(id);
      }
    }
    // Project governance is shared context. A common document does not imply
    // that unrelated API contracts are relevant to this work branch.
    for(const doc of arr(s.documents))if(handoffGovernance(doc)&&
       !String(doc.source_ref||'').includes('[owning matrix projection source]'))
      add(doc.id,'Явная нормативная инструкция проекта');
    while(waiting.length){
      const id=waiting.shift(),c=contracts.get(id),m=modules.get(id);
      if(c){
        if(c.module)add(c.module,'Владелец контракта '+id);
        else issues.push('Отсутствует owning module контракта '+id);
        arr(c.docs).forEach(d=>add(d,'Документ контракта '+id));
        arr(c.dependencies).forEach(dep=>{
          const key=typeof dep==='string'?dep:dep?.contract_id||dep?.module_id||dep?.id;
          if(key)add(key,'Declared dependency контракта '+id);
          else issues.push('Неопределённая зависимость контракта '+id);
        });
      }else if(m){
        arr(m.docs).forEach(d=>add(d,'Документ модуля '+id));
        arr(m.dependencies).forEach(dep=>{
          const key=typeof dep==='string'?dep:dep?.module_id||dep?.id;
          if(key&&modules.has(key))add(key,'Declared dependency модуля '+id);
          else if(key)issues.push('Отсутствует модуль '+key+' для '+id);
          else issues.push('UNKNOWN: нераспознанная зависимость модуля '+id);
        });
      }
    }
    for(const id of unprovenInterfaces)if(!linkedContracts.has(id)&&!linkedModules.has(id))
      issues.push('UNKNOWN: применимость связанного интерфейса '+id+
        ' не подтверждена work-binding или зависимостью; это только связь для проверки текущим writer');
    const pinned=new Set(arr(s.atlas.source_pins).map(pin=>
      pin.path+'|'+pin.sha256+'|'+pin.bytes));
    const usedDocSha=new Set(),docManifest=[],docBodies=[];
    for(const [id,reason] of linkedDocs){
      const doc=docs.get(id),identity=doc?.path+'|'+doc?.sha256+'|'+doc?.bytes;
      if(!doc||!pinned.has(identity)){
        issues.push('Нет проверенного source pin документа: '+id);
        continue;
      }
      if(typeof doc.content!=='string'){
        issues.push('Отсутствует тело документа: '+id);
        continue;
      }
      const unique=doc.sha256+':'+doc.bytes;
      const isDuplicate=usedDocSha.has(unique);
      docManifest.push({id,title:doc.title,path:doc.path,sha256:doc.sha256,
        bytes:doc.bytes,source_ref:doc.source_ref,reason,
        included:!isDuplicate,duplicate:isDuplicate});
      if(isDuplicate)continue;
      usedDocSha.add(unique);
      let body=handoffRedact(doc.content),language='text';
      if(doc.kind==='json'){
        try{body=handoffJSON(JSON.parse(doc.content));language='json';}
        catch(_){issues.push('JSON документ требует проверки: '+id);}
      }
      docBodies.push('### '+handoffRedact(doc.title)+' · '+id+'\n'+
        'Путь: '+handoffRedact(doc.path)+' | SHA256 original: '+doc.sha256+
        ' | Байт: '+doc.bytes+' | Связь: '+handoffRedact(reason)+'\n\n'+
        handoffFence(body,language));
    }
    const participants=new Map();
    for(const id of [...unfinishedIds,...outside.keys(),...ancestorIds]){
      const work=model.byId.get(id);
      for(const id of [...actors(work),...sourceActors(model,work.id),
          ...observationActors(model,work.id)]){
        if(typeof id==='string'&&id&&id!=='UNKNOWN')
          participants.set(id,model.participants.get(id)||{id,role:'UNKNOWN'});
      }
    }
    const project=s.atlas.project||{};
    if(project.writer)participants.set(project.writer,
      model.participants.get(project.writer)||{id:project.writer,role:'writer'});
    const ancestorContext=ancestorIds.map(id=>{
      const work=model.byId.get(id),ev=model.sourceLatest.get(id);
      return {id,title:workDisplayTitle(model,work),
        role:'ANCESTOR_CONTEXT_ONLY_NOT_AN_EXECUTION_TARGET',
        source_done:ev?ev.status==='done':work.state==='ACCEPTED',
        work_record:work,source_step:model.sourceSteps.get(id)||'UNKNOWN',
        source_latest:ev||'UNKNOWN',source_ownership:model.ownership.get(id)||'UNKNOWN'};
    });
    const underReview=excluded.filter(row=>
      row.source_status==='done'&&!row.source_accepted);
    const context={
      schema:selection?'atlas.work-handoff-selection/v1':'atlas.work-handoff-unfinished/v1',
      generated_from_snapshot_at:s.atlas.as_of||'UNKNOWN',
      ...(hasLocalizedFields(s)?{display_project:displayProjectProjection(model),original_project:project}:{}),
      project:{id:project.id,title:project.title,objective:hasLocalizedFields(s)?displayText(model,project.id,'project.objective'):project.objective,
        writer:project.writer,authority_ref:project.authority_ref,
        scope_note:hasLocalizedFields(s)?displayText(model,project.id,'project.scope_note'):project.scope_note,source_ref:project.source_ref,...(selection?{display_title:projectDisplayTitle(s),display_title_source:'owning source matrix.project; descriptive suffix removed; authority identity unchanged'}:{})},
      selected_work:{id:selection?.all?'ALL':root.id,title:selection?.all?projectDisplayTitle(s):workDisplayTitle(model,root),
        original_title:root.title,
        source_status:model.sourceLatest.get(root.id)?.status||'UNKNOWN'},
      examined_in_selected_subtree:subtree.length,
      unfinished_blocks:selection?target.filter(x=>!x.done).length:target.length,source_done_excluded:excluded.filter(x=>x.done).length,...(selection?{selected_work_ids:target.map(x=>x.work.id),selection_scope:selection.all?'ALL_WORKS':'SUBTREE',unselected_context_count:excluded.length}:{}),
      source_done_without_accepted_true:underReview.length,
      completion_rule:'Current owning SOURCE status done means shown Выполнено; without SOURCE only Atlas ACCEPTED excludes. Never infer parent completion from child status.',
      evidence_levels:'SOURCE / TEST / INSTALLED / RUNTIME / BUSINESS / USER_RESULT remain distinct',
      limits:[selection?.all?'Only explicit selected_work_ids across this snapshot can be execution targets':'Only works in selected subtree can be execution targets',
        'External prerequisites and completed ancestors are context, never new tasks',
        'The source snapshot may be stale; verify fresh writer, lease and source before executing',
        'Copy does not write work events, create permissions or install code.']
    };
    const outline=detail.map(row=>({
      id:row.id,title:row.display_title,source_status:row.source_status,
      source_accepted:row.source_accepted,atlas_state:row.atlas_state,
      parent_id:row.parent_id,tree_path:row.tree_path,
      dependencies:row.dependencies,next_owner:row.work_record.writer
    }));
    const blocks=[
      selection?'# Atlas — точное ТЗ выбранных работ':'# Atlas — только невыполненные работы выбранной ветки',
      '**Выбрано:** '+handoffRedact(selection?.all?projectDisplayTitle(s):workDisplayTitle(model,root))+' ('+(selection?.all?'ALL':root.id)+')',
      (selection?'**Выбранных заданий:** ':'**Невыполненных блоков:** ')+target.length+
        (selection?' · **Вне списка исполнения:** ':' · **Исключено со статусом «Выполнено»:** ')+excluded.length+'.',
      '**Приёмка отдельно:** '+underReview.length+
        ' исключённых работ SOURCE done имеют accepted≠true; это не доказанная приёмка.',
      '## 1. Контекст и границы выбранной ветки\n'+handoffFence(handoffJSON(context),'json'),
      (selection?'## 2. Точный список выбранных заданий\n':'## 2. Невыполненные блоки на всех уровнях вложенности\n')+
        handoffFence(handoffJSON(outline),'json'),
      (selection?'## 3. Полное содержание выбранных заданий\n':'## 3. Полное содержание только невыполненных блоков\n')+
        handoffFence(handoffJSON(detail),'json'),
      '## 4. Родители вне списка исполнения — только контекст\n'+
        handoffFence(handoffJSON(ancestorContext),'json'),
      '## 5. Внутренние и внешние зависимости\n'+handoffFence(handoffJSON({
        edges,external_context:[...outside.values()],
        relations:arr(s.input.relations).filter(edge=>
          linkedContracts.has(edge.from)||linkedContracts.has(edge.to)||
          linkedModules.has(edge.from)||linkedModules.has(edge.to))}),'json'),
      '## 6. Применимые модули и контракты с полными полями\n'+
        handoffFence(handoffJSON({
          modules:[...linkedModules].map(([id,reason])=>({reason,record:modules.get(id)})),
          contracts:[...linkedContracts].map(([id,reason])=>({reason,record:contracts.get(id)}))}),'json'),
      '## 7. Доказанные документы и их SHA256\n'+
        handoffFence(handoffJSON(docManifest),'json')+'\n'+
        (docBodies.length?docBodies.join('\n\n'):
         'Нормативные тела не подтверждены в этой области; см. пробелы ниже.'),
      '## 8. Участники и маршруты прав\n'+handoffFence(handoffJSON({
        participants:[...participants.values()],writer:project.writer,
        authority_ref:project.authority_ref,
        copy_does_not_grant_authority:true}),'json'),
      '## 9. Пробелы / UNKNOWN / следующий владелец\n'+handoffFence(handoffJSON({
        issues:[...new Set(issues)],source_matrix_status:model.source.status,
        no_automatic_acceptance:true,runtime_proven:false,
        next_owner:project.writer||'UNKNOWN'}),'json'),
      '## 10. Правила продолжения\n'+[
        '1. Сверить текущий source snapshot, исходную матрицу, полномочия, writer и lease.',
        '2. Исполнять только ID раздела 2; completed предки и external dependencies лишь контекст.',
        '3. Недостающие контракты и документы сначала восстановить адресно через текущего writer.',
        '4. Проверить тесты/доказательства в точной требуемой области; SOURCE не означает runtime или business.',
        '5. Вернуть принятый результат текущему владельцу матрицы, обновить Atlas штатным checkpoint и readback.'
      ].join('\n')
    ];
    if(!target.length)blocks.splice(4,0,
      '**В выбранной ветке нет невыполненных блоков в этом снимке. Новое исполнение не требуется.**');
    const base=blocks.join('\n\n');
    if(contextOnly===true)return base;
    if(selection)return base+'\n\n## 11. Режимы, модели и возврат результата\n'+coordinationRules()+'\n\nИсполнять только selected_work_ids и список раздела2. Работы любого статуса вне этого списка — только контекст; completed выбранные работы означают передачу фактов для анализа, не разрешение повторить выполненные эффекты. Вернуть work IDs, входную редакцию, факты, артефакты/SHA, проверки, ограничения, остаток, delta документов/матрицы, operation/event ID и опубликованный readback. Нет доступа к записи → вернуть подготовленный delta действующему writer, не объявлять публикацию.';
    const plan=coordinationPlan(s,root,outline),rules=coordinationRules();
    const assignments=plan.agent_room.blocks.map(block=>({...block,
      return_to:'Проверенный Codex0 и секретарь существующей комнаты; actual routes UNKNOWN до проверки',
      execution_scope:'ТОЛЬКО work_ids этого назначения. Остальной текст — контекст, не дополнительные задания.',
      rules_included:true}));
    // Individual packets are generated on demand, never multiplied in the root clipboard body.
    if(contextOnly==='workers')return assignments.map(assignment=>({assignment,
      markdown:'# Пакет исполнителя: '+handoffRedact(assignment.proposed_chat_title)+'\n\n'+
        rules+'\n\n'+handoffFence(handoffJSON(assignment),'json')+'\n\n'+
        buildUnfinishedHandoff(s,assignment.branch_root,true)}));
    return base+'\n\n## 11. Два режима, модели и возврат результатов\n\n'+rules+
      '\n\n'+handoffFence(handoffJSON(plan),'json')+
      '\n\n## 12. Назначения исполнителей — общий нормативный контекст выше\n\n'+
      (assignments.length?handoffFence(handoffJSON(assignments),'json')+
        '\n\nКаждому исполнителю передать общие правила раздела 11, его точное назначение и полные применимые нормативные тела разделов 1–9. Заголовок назначения отдельно не является самодостаточным пакетом. Не сокращать договорённости и evidence до ссылок. Для отдельных полных Markdown используйте buildExecutorHandoffs(snapshot, workId); каждый возвращённый markdown включает правила, назначение и свой полный контекст. Без доступного API передать весь этот пакет, явно ограничив исполнение work_ids назначения. Общие тела здесь хранятся один раз, без размножения в буфере.':
        'Невыполненных работ нет. Исполнение, распределение и найм не требуются.');
  }
  function projectDisplayTitle(s){
    const value=matrixSource(s).data?.project,suffix=' — матрица работ';
    if(typeof value==='string'&&value.trim()){const title=value.trim();return title.endsWith(suffix)?title.slice(0,-suffix.length):title}
    if(value&&typeof value==='object'&&typeof value.title==='string'&&value.title.trim())return value.title.trim();
    return s.atlas?.project?.title||s.input?.project?.title||'UNKNOWN';
  }
  function atlasStatusIds(s,scopeId=null,kind=null,leafOnly=false){
    const m=buildPresentation(s),rows=scopeId?incompleteTreeScope(m,scopeId):[...m.byId.keys()].map(id=>incompleteTreeScope(m,id)[0]);
    return rows.filter(row=>(!leafOnly||!arr(m.children.get(row.work.id)).length)&&(!kind||atlasStatusKind(m,row.work.id)===kind)).map(row=>row.work.id);
  }
  function atlasStatusKind(m,id){const raw=m.sourceLatest.get(id)?.status;return raw||({ACCEPTED:'done',DOING:'doing',BLOCKED:'blocked',PLANNED:'planned',REVIEW:'review',PARTIAL:'partial',WAITING:'waiting',PAUSED:'paused',CANCELLED:'cancelled'}[m.byId.get(id)?.state]||'unknown')}
  function atlasStatusDistribution(s,id){const out=new Map(),m=buildPresentation(s);for(const key of atlasStatusIds(s,id,null,true)){const kind=atlasStatusKind(m,key);if(!out.has(kind))out.set(kind,[]);out.get(kind).push(key)}return out}
  function buildSelectedHandoff(s,ids,scopeId=null){
    const m=buildPresentation(s),root=scopeId||m.byId.keys().next().value;if(!root)throw Error('ATLAS_HANDOFF_EMPTY_PROJECT');
    return buildUnfinishedHandoff(s,root,false,{all:!scopeId,ids:[...new Set(ids)]});
  }
  function buildExecutorHandoffs(s,workId){
    const packets=buildUnfinishedHandoff(s,workId,'workers');
    return Array.isArray(packets)?packets:[];
  }
  async function buildWorkHandoffCompanion(s, workId, options = null) {
    const body = options?.unfinishedOnly ? buildUnfinishedHandoff(s,workId) : buildWorkHandoff(s,workId), bytes = new TextEncoder().encode(body);
    // No external crypto/library/network. A digest is mandatory before claiming a verifiable companion.
    const subtle = typeof globalThis !== 'undefined' ? globalThis.crypto?.subtle : undefined;
    if (!subtle || typeof subtle.digest !== 'function') throw Error('ATLAS_HANDOFF_SHA256_UNAVAILABLE');
    const digest = await subtle.digest('SHA-256', bytes);
    const body_sha256 = [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
    const manifest = {
      schema:'atlas.work-handoff-companion/v1',content_type:'text/markdown; charset=utf-8',
      source_snapshot_at:s.atlas.as_of || 'UNKNOWN',
      project_id:s.atlas.project?.id || 'UNKNOWN',work_id:workId,
      release_id:s.input.release?.id || 'UNKNOWN',input_sha256:s.input_sha256 || 'UNKNOWN',
      body_sha256,body_bytes:bytes.byteLength,
      ...(options?.unfinishedOnly ? {copy_scope:'UNFINISHED_SELECTED_SUBTREE'} : {}),
      extraction:'SHA256 of exact UTF-8 bytes immediately after the body marker through the end of file',
      notes:['This file contains sanitized copied context from one immutable Atlas snapshot',
        'Source body hashes inside the handoff identify original source bytes, not sanitized copy',
        'No write, permission grant, installed/runtime acceptance or live observation is implied']
    };
    const marker = '<!-- ATLAS_HANDOFF_BODY_START -->\n';
    const text = '<!-- ATLAS_COMPANION_MANIFEST_BEGIN -->\n' + JSON.stringify(manifest,null,2)
      + '\n<!-- ATLAS_COMPANION_MANIFEST_END -->\n' + marker + body;
    const filePart=value=>String(value).replace(/[^a-z0-9._-]/giu,'_').slice(0,90) || 'UNKNOWN';
    const filename=['ATLAS',filePart(manifest.project_id),filePart(workId),filePart(manifest.release_id),...(options?.unfinishedOnly ? ['UNFINISHED'] : [])].join('-')+'.md';
    return {filename, text, manifest, body};
  }
  // W1.06: only view state migrates between snapshots; evidence always comes from this snapshot.
  function ownerDatasetIdentity(s, model = buildPresentation(s)) {
    return JSON.stringify([s.atlas?.project?.id || '', model.matrix?.schema || 'atlas-native',
      model.source.document?.source_ref || s.atlas?.project?.source_ref || 'native:' + s.atlas?.project?.id]);
  }
  function ownerRestoreState(saved, s, model = buildPresentation(s)) {
    if (!saved || typeof saved !== 'object') return null;
    const sameRelease = saved.release === s.input.release.id && saved.input_sha256 === s.input_sha256;
    if (saved.version === 2 ? saved.dataset !== ownerDatasetIdentity(s, model) : saved.version !== 1 || !sameRelease) return null;
    const ids = values => [...new Set(arr(values).filter(id => typeof id === 'string' && model.byId.has(id)))];
    const positions = {}, nested = {};
    Object.entries(saved.panels || {}).forEach(([id, value]) => { if (model.byId.has(id) && Number.isFinite(value) && value >= 0) positions[id] = Math.min(value, 1e7); });
    const validKeys = new Set(['owner-extra']);
    model.byId.forEach((_, id) => ['owner-observations-', 'owner-definition-', 'owner-atlas-'].forEach(prefix => validKeys.add(prefix + id)));
    model.participants.forEach((_, id) => validKeys.add('owner-actor-' + id));
    Object.entries(saved.nested || {}).forEach(([key, value]) => { if (validKeys.has(key) && typeof value === 'boolean') nested[key] = value; });
    const allowedStates = ['all', 'journal:doing', ...Object.keys(STATES), ...['done','doing','partial','waiting','planned','blocked','review','paused','cancelled'].map(x => 'source:' + x)];
    const actorExists = typeof saved.actor === 'string' && (model.participants.has(saved.actor) || [...model.observationMap.keys()].some(id => observationActors(model, id).includes(saved.actor)));
    return {expanded: ids(saved.expanded), filterCollapsed: ids(saved.filterCollapsed), details: ids(saved.details),
      panels: positions, nested, roster: saved.roster === true, auto: saved.auto === true,
      query: typeof saved.query === 'string' ? saved.query.slice(0, 10000) : '', actor: actorExists ? saved.actor : '',
      workState: allowedStates.includes(saved.workState) ? saved.workState : 'all', activeOnly: saved.activeOnly === true,
      scrollX: Number.isFinite(saved.scrollX) ? Math.max(0, Math.min(saved.scrollX, 1e7)) : 0,
      scrollY: Number.isFinite(saved.scrollY) ? Math.max(0, Math.min(saved.scrollY, 1e7)) : 0,
      releaseChanged: !sameRelease};
  }
  function ownerNativeCurrent(model, item, now, previous) {
    const actor = item.activity?.actor;
    return !arr(model.children.get(item.id)).length && activityState(item, now, previous) === 'CURRENT'
      && typeof actor === 'string' && !!actor.trim() && actor !== 'UNKNOWN' && model.participants.has(actor)
      && model.participants.get(actor).activity_eligible !== false && Date.parse(item.activity.observed_at) <= model.at;
  }
  function ownerCurrentSummary(model, now = Date.now(), agedNative, agedSource) {
    const current = new Map(), actorIds = new Set(); let latest = null;
    const remember = (id, at) => {
      const time = Date.parse(at);
      if (model.byId.has(id) && !arr(model.children.get(id)).length && Number.isFinite(time) && time <= Math.min(now, model.at)
          && (!latest || time > Date.parse(latest.at))) latest = {step_id: id, at};
    };
    arr(model.matrix?.activity_events).forEach(e => remember(e.step_id, e.at));
    model.byId.forEach((item, id) => {
      const leaf = !arr(model.children.get(id)).length;
      const source = sourceActivity(model, id, now, agedSource?.get(id));
      remember(id, item.activity?.observed_at);
      const ids = new Set(source.state === 'CURRENT' ? source.observations.map(e => e.actor_id) : []);
      const a = item.activity?.actor;
      if (ownerNativeCurrent(model, item, now, agedNative?.get(id))) ids.add(a);
      if (leaf && ids.size) { current.set(id, [...ids]); ids.forEach(x => actorIds.add(x)); }
    });
    return {steps: current.size, actors: actorIds.size, actorIds: [...actorIds], current, latest,
      qualification: 'SAVED_EXACT_LEAF_PROOFS_ONLY_INCOMPLETE_SESSION_COVERAGE'};
  }
  function ownerFormatDuration(milliseconds) {
    if (!Number.isFinite(milliseconds) || milliseconds < 0) return '—';
    let minutes = Math.floor(milliseconds / 60000);
    if (!minutes) return '<1m';
    const days = Math.floor(minutes / 1440); minutes %= 1440;
    const hours = Math.floor(minutes / 60); minutes %= 60;
    return [days ? days + 'd' : '', hours ? hours + 'h' : '', minutes ? minutes + 'm' : ''].filter(Boolean).join(' ');
  }
  function ownerDuration(model, item, now = Date.now(), nativePrevious, sourcePrevious) {
    const at = Math.min(now, model.at);
    const records = eventOrder([...arr(model.eventMap.get(item.id)), ...arr(model.matrix?.activity_events).filter(e => e?.step_id === item.id), ...arr(item.events)]);
    const reported = records.filter(e => {
      const p = e.duration_evidence;
      return Number.isFinite(e.reported_duration_minutes) && e.reported_duration_minutes >= 0 && p?.source === 'chatgpt_ui'
        && p.step_id === item.id && model.participants.has(p.actor_id) && typeof p.ref === 'string' && p.ref.trim()
        && Number.isFinite(Date.parse(e.at)) && Date.parse(e.at) <= at && Number.isFinite(Date.parse(p.observed_at)) && Date.parse(p.observed_at) <= Date.parse(e.at);
    }).slice(-1)[0];
    if (reported) return {text: ownerFormatDuration(reported.reported_duration_minutes * 60000),
      note: 'Длительность из записанного источника ChatGPT UI · наблюдалось ' + reported.duration_evidence.observed_at,
      evidence: {reported_duration_minutes: reported.reported_duration_minutes, duration_evidence: reported.duration_evidence},
      perActor: [{actor_id: reported.duration_evidence.actor_id, text: ownerFormatDuration(reported.reported_duration_minutes * 60000)}]};
    const source = sourceActivity(model, item.id, now, sourcePrevious);
    const evidenceRef = (x, e) => typeof x === 'string' ? !!x.trim() : x && typeof x === 'object' && [x.ref, x.path].some(v => typeof v === 'string' && v.trim()) && (x.actor_id === undefined || x.actor_id === e.actor_id) && (x.step_id === undefined || x.step_id === item.id);
    const candidates = source.state === 'CURRENT' ? source.observations.slice() : [];
    const a = item.activity;
    if (ownerNativeCurrent(model, item, now, nativePrevious))
      candidates.push({...a, actor_id: a.actor, at: a.observed_at});
    const perActor = new Map();
    candidates.forEach(e => {
      const start = Date.parse(e.observed_started_at), observed = Date.parse(e.at);
      if (!Number.isFinite(start) || start > observed || !arr(e.observed_start_evidence).some(x => evidenceRef(x, e))) return;
      perActor.set(e.actor_id, {actor_id: e.actor_id, text: ownerFormatDuration(now - start),
        observed_started_at: e.observed_started_at, evidence: e.observed_start_evidence});
    });
    const values = [...perActor.values()];
    return values.length ? {text: values.length === 1 ? values[0].text : '—', perActor: values,
      note: 'Календарный интервал от подтверждённого начала; отображается, пока подтверждение активности действительно. Несколько исполнителей показаны отдельно; это не трудозатраты или CPU.', evidence: values}
      : {text: '—', perActor: [], note: 'Начало/длительность не подтверждены; старые doing не суммируются', evidence: null};
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = {derive, reset, openEntity, exportIndex, openWork, activityState, criterionProgress, actors,
    projectDisplayTitle, atlasStatusIds, atlasStatusDistribution, buildSelectedHandoff, matrixSource, buildPresentation, workDisplayTitle, sourceActors, sourceActivity, roadmapRows, presentationHistory, eventOrder, routeFor, parseRoute, exportMatrix, buildWorkHandoff, buildUnfinishedHandoff, buildExecutorHandoffs, buildWorkHandoffCompanion, countOwnerStatuses, ownerDatasetIdentity, ownerRestoreState, ownerCurrentSummary, ownerFormatDuration, ownerDuration, HANDOFF_SCHEMA, PRESENTATION, displaySHA, displayField, displayText, displayWorkProjection, displayProjectProjection};
  if (typeof document === 'undefined') return;
  const byId = id => document.getElementById(id);
  const snapshot = JSON.parse(byId('navigator-data').textContent);
  const isAtlas = !!snapshot.atlas;
  const presentation = isAtlas ? buildPresentation(snapshot) : null;
  const state = {tab: isAtlas ? 'works' : 'overview', query: '', module: '', lifecycle: 'current', selection: null, selectionKind: null, workState: 'all', actor: '', activeOnly: false,
    expanded: new Set(isAtlas && presentation.matrix ? [] : works(snapshot).map(w => w.id)), filterCollapsed: new Set()};
  if (isAtlas && presentation.matrix) {
    const initial = presentation.matrix.coverage && presentation.matrix.coverage.current_stage;
    if (presentation.byId.has(initial)) state.expanded.add(initial);
    presentation.byId.forEach((w, id) => {
      const recorded = presentation.sourceLatest.get(id);
      if ((!recorded || recorded.status !== 'doing') && w.state !== 'DOING' && sourceActivity(presentation, id, Date.now()).state !== 'CURRENT') return;
      let p = presentation.parent.get(id); while (p !== null && p !== undefined) { state.expanded.add(p); p = presentation.parent.get(p); }
    });
  }
  const agedActivity = new Map();
  const agedSourceActivity = new Map();
  // Owner-supplied matrix presentation. Only view state lives here; snapshot/model stay immutable.
  const ownerPane = byId('detail'), ownerPaneHome = ownerPane.parentElement;
  const ownerView = {details: new Set(), roster: false, panels: {}, nested: {}, auto: false, storage: false, lastInteraction: 0};
  const ownerViewKey = isAtlas ? 'atlas:owner-matrix:view:v1:' + snapshot.atlas.project.id : '';
  if (isAtlas && typeof window !== 'undefined') {
    try {
      const store = window.sessionStorage;
      if (store) {
        const saved = JSON.parse(store.getItem(ownerViewKey) || 'null');
        store.setItem(ownerViewKey, JSON.stringify(saved)); ownerView.storage = true;
        const restored = ownerRestoreState(saved, snapshot, presentation);
        if (restored) {
          state.expanded = new Set(restored.expanded); state.filterCollapsed = new Set(restored.filterCollapsed);
          ownerView.details = new Set(restored.details); ownerView.roster = restored.roster; ownerView.auto = restored.auto;
          ownerView.panels = restored.panels; ownerView.nested = restored.nested;
          ownerView.restore = restored; ownerView.releaseChanged = restored.releaseChanged;
        }
      }
    } catch (_) { ownerView.storage = false; ownerView.auto = false; }
  }
  function displaySourceActivity(id) {
    const result = sourceActivity(presentation, id, Date.now(), agedSourceActivity.get(id));
    agedSourceActivity.set(id, result.state); return result;
  }
  function applyRoute(hash) {
    const route = parseRoute(hash, snapshot); reset(state); Object.assign(state, route); state.error = route.error || null; state.activeOnly = false; state.filterCollapsed.clear();
    if (route.selectionKind === 'work') {
      let p = presentation.parent.get(route.selection); while (p !== null && p !== undefined) { state.expanded.add(p); p = presentation.parent.get(p); }
      ownerView.details.add(route.selection);
    }
    if (route.selectionKind === 'entity') { const item = find(snapshot, route.selection); state.lifecycle = item && item.lifecycle || 'current'; }
  }
  function goRoute(hash) {
    if (!isAtlas) return;
    applyRoute(hash);
    if (typeof window !== 'undefined' && window.location && window.location.hash !== hash) window.location.hash = hash;
    render();
  }
  function entityRoute(id) {
    return routeFor(arr(snapshot.documents).some(d => d.id === id) ? 'document' : arr(snapshot.input.contracts).some(c => c.id === id) ? 'contract' : 'module', id);
  }
  function displayActivity(item) {
    const value = activityState(item, Date.now(), agedActivity.get(item.id));
    agedActivity.set(item.id, value); return value;
  }
  function node(tag, value, className) {
    const result = document.createElement(tag);
    if (value !== undefined && value !== null) result.textContent = String(value);
    if (className) result.className = className;
    return result;
  }
  function line(parent, label, value) {
    const row = node('div', null, 'field'); row.append(node('strong', label), node('div', textValue(value))); parent.append(row); return row;
  }
  function raw(parent, label, value) {
    const box = node('details', null, 'raw-data'); box.append(node('summary', label), node('pre', JSON.stringify(value, null, 2))); parent.append(box);
  }
  function linkButton(id, kind) {
    const item = kind === 'work' ? findWork(snapshot, id) : find(snapshot, id);
    const b = node('button', item ? `${workDisplayTitle(presentation,item)} · ${id}` : id, 'link'); b.dataset[kind === 'work' ? 'work' : 'entity'] = id;
    if (!item) { b.disabled = true; b.title = 'Объект отсутствует в данном снимке'; }
    return b;
  }
  function links(parent, label, values, kind = 'entity') {
    const row = node('div', null, 'field'); row.append(node('strong', label));
    if (!arr(values).length) row.append(node('span', ' —'));
    arr(values).forEach(id => row.append(linkButton(id, kind))); parent.append(row);
  }
  function badges(item) {
    const p = node('p', null, 'badges');
    [item.lifecycle === 'archived' ? '📚 Архив' : item.lifecycle ? '📌 Текущая версия' : null, item.evidence_state, item.execution].filter(Boolean).forEach(v => p.append(node('span', v, 'badge')));
    return p;
  }
  function issues(parent, values) {
    if (!arr(values).length) return;
    const box = node('details', null, 'issues'); box.append(node('summary', `Needs attention: ${values.length}`));
    values.forEach(value => box.append(node('p', typeof value === 'string' ? value : JSON.stringify(value)))); parent.append(box);
  }
  function workBadges(item) {
    const p = node('div', null, 'badges work-badges');
    p.append(node('span', `Recorded state: ${textValue(item.state)} · ${STATES[item.state] || 'UNKNOWN'}`, `badge state-${STATES[item.state] ? item.state.toLowerCase() : 'unknown'}`));
    const active = displayActivity(item);
    p.append(node('span', `Activity: ${active} · ${ACTIVITY[active]}`, `badge activity-${active.toLowerCase()}`));
    return p;
  }
  function patchDetail(parent, artifact) {
    const patch = artifact.patch; if (!patch) return;
    const p = node('div', null, 'patch'); p.append(node('h4', `Patch · ${textValue(patch.state)}`));
    line(p, 'Целевой артефакт', patch.target_id); line(p, 'SHA256 базовой версии', patch.base_sha256);
    line(p, 'Область изменения', arr(patch.selectors).length ? patch.selectors.join(', ') : 'Не указано');
    line(p, 'Доказательство решения', arr(patch.decision_evidence_ids).length ? patch.decision_evidence_ids.join(', ') : 'Не указано');
    line(p, 'Результирующий артефакт', patch.result_artifact_id || 'Не закреплено'); parent.append(p);
  }
  function actorChips(parent, ids, label) {
    const unique = [...new Set([].concat(ids || []).filter(x => typeof x === 'string' && x))];
    if (!unique.length) return;
    const row = node('div', null, 'actor-chips');
    if (label) row.append(node('span', label + ': ', 'note'));
    unique.forEach(id => { const a = presentation.participants.get(id), b = node('button', a && a.label || id, 'link actor-chip'); b.dataset.actor = id; row.append(b); });
    parent.append(row);
  }
  function sourceReferences(parent, references) {
    if (!arr(references).length) { parent.append(node('p', 'Ссылки на первичные источники не приложены.', 'note')); return; }
    arr(references).forEach(ref => {
      const rawRef = typeof ref === 'string' ? ref : ref && ref.ref;
      const doc = rawRef && arr(snapshot.documents).find(d => d.path === rawRef || d.source_ref === rawRef || typeof d.source_ref === 'string' && d.source_ref.startsWith(rawRef + ' ['));
      if (doc) links(parent, typeof ref === 'object' && ref.label || 'Исходный документ', [doc.id]);
      parent.append(node('pre', typeof ref === 'string' ? ref : JSON.stringify(ref, null, 2), 'reference-data'));
    });
  }
  function sourceEventDetail(parent, event, origin) {
    const box = node('details', null, 'source-event');
    box.append(node('summary', `${event.at || 'UNKNOWN'} · ${event.id || 'UNKNOWN'} · ${event.status || event.state || origin || 'Записанное событие'}`));
    if (event.note) box.append(node('p', event.note));
    if (Object.prototype.hasOwnProperty.call(event, 'accepted')) line(box, 'Acceptance recorded by the source', event.accepted);
    SOURCE_ROLES.forEach(key => actorChips(box, event[key], {executor_ids: 'Executors', contributor_ids: 'Contributors', reviewer_ids: 'Reviewers', history_ids: 'History participants', coordinator_id: 'Coordinator'}[key]));
    if (event.actor_id) actorChips(box, event.actor_id, 'Participant');
    if (event.valid_until) line(box, 'Recorded observation valid until', event.valid_until);
    sourceReferences(box, event.evidence);
    raw(box, 'Точное событие источника (JSON)', event); parent.append(box);
  }
  function sourceWorkDetail(target, item) {
    const step = presentation.sourceSteps.get(item.id); if (!step) return;
    const latest = presentation.sourceLatest.get(item.id), own = presentation.ownership.get(item.id), activity = displaySourceActivity(item.id);
    const box = node('section', null, 'source-work-detail'); box.append(node('h3', 'Запись исходной матрицы работ'));
    line(box, 'Редакция источника / время снимка', `${textValue(presentation.matrix.revision)} · ${textValue(presentation.matrix.updated_at)}`);
    if (step.scope_note) line(box, 'Область / записанный результат', displayText(presentation,step.id,'work.scope_note'));
    if (step.source_definition) raw(box, 'Исходное определение шага', step.source_definition);
    if (latest) {
      line(box, 'Последнее событие источника на момент снимка', `${latest.id} · ${latest.at} · ${latest.status}`);
      line(box, 'Приёмка источника / область', `${latest.accepted === true ? 'Принято источником в указанной области' : latest.accepted === false ? 'Источник не принял результат' : 'UNKNOWN'}. This does not create a new Atlas acceptance decision.`);
      if (latest.note) box.append(node('p', latest.note));
    }
    SOURCE_ROLES.forEach(key => actorChips(box, own[key], {executor_ids: 'Executors', contributor_ids: 'Contributors', reviewer_ids: 'Reviewers', history_ids: 'History participants', coordinator_id: 'Coordinator'}[key]));
    line(box, 'Наблюдение активности в источнике', `${activity.state} · ${activity.reason}`);
    activity.observations.forEach(e => line(box, `${e.actor_id} → ${e.step_id}`, `${e.at} · until ${textValue(e.valid_until)} · ${e.id}`));
    box.append(node('p', 'Ссылки источника — сохранённые записи. Путь, команда, статус или хеш сами по себе не являются новой проверенной квитанцией. Длительность не выводится из времени создания или старого статуса «в работе».', 'note'));
    const history = node('details', null, 'source-history'); history.append(node('summary', `Complete source work history · ${arr(presentation.eventMap.get(item.id)).length} events`));
    arr(presentation.eventMap.get(item.id)).forEach(e => sourceEventDetail(history, e)); box.append(history);
    raw(box, 'Точная запись шага источника (JSON)', presentation.matrix.steps.find(s => s.id === item.id));
    if (presentation.source.document) links(box, 'Закреплённая исходная матрица', [presentation.source.document.id]);
    target.append(box);
  }
  function workDetail(item, target = byId('detail')) {
    target.replaceChildren();
    target.append(node('div', item.id, 'eyebrow'), node('h2', workDisplayTitle(presentation,item)), workBadges(item));
    if (isAtlas) sourceWorkDetail(target, item);
    line(target, 'Цель', displayText(presentation,item.id,'work.objective')); line(target, 'Ожидаемый результат', workDisplayField(item,'outcome'));
    const ownership = node('div', null, 'field-grid');
    line(ownership, 'Владелец записи', item.writer); line(ownership, 'Назначено', arr(item.assigned_to).length ? item.assigned_to.join(', ') : item.assigned_to);
    line(ownership, 'Принятые критерии', criterionProgress(item));
    line(ownership, 'Ранее выполняли', arr(item.derived && item.derived.completed_by).length ? item.derived.completed_by.join(', ') : 'UNKNOWN');
    target.append(ownership);
    if (item.activity) {
      const a = node('div', null, 'activity-info');
      line(a, 'Наблюдение активности', `${textValue(item.activity.actor)} · observed ${textValue(item.activity.observed_at)} · valid until ${textValue(item.activity.valid_until)}`);
      line(a, 'Доказательство активности', item.activity.evidence_id); target.append(a);
    }
    links(target, 'Родительская работа', item.parent_id ? [item.parent_id] : [], 'work');
    links(target, 'Дочерние работы', works(snapshot).filter(x => x.parent_id === item.id).map(x => x.id), 'work');
    links(target, 'Зависит от', item.depends_on, 'work');
    line(target, 'Разрешённые пути записи', arr(item.write_scope).length ? item.write_scope.join('\n') : 'Не указано');
    if (item.blocker) {
      const b = node('section', null, 'blocker'); b.append(node('h3', 'Блокер')); line(b, 'Причина', item.blocker.reason);
      line(b, 'Условие снятия блокировки', item.blocker.unblock_condition); line(b, 'Кто устраняет блокировку', item.blocker.next_owner); target.append(b);
    }
    line(target, 'Записанный результат', item.result); line(target, 'Осталось', workDisplayField(item,'remaining'));
    line(target, 'Следующее действие', item.next_action ? `${textValue(item.next_action.actor)} · ${textValue(workDisplayField(item,'next_action'))}` : 'Не указано');
    issues(target, item.derived && item.derived.issues);
    target.append(node('h3', 'Критерии и решения о приёмке'));
    if (!arr(item.criteria).length) target.append(node('p', 'Критерии не указаны', 'note'));
    arr(item.criteria).forEach(c => {
      const box = node('section', null, 'criterion'); box.append(node('h4', `${c.id} · ${c.text}`));
      line(box, 'Обязательный уровень доказательства', c.required_scope);
      const decisions = arr(item.acceptance).filter(a => a.criterion_id === c.id);
      if (!decisions.length) box.append(node('p', 'Решение о приёмке не записано', 'note'));
      decisions.forEach(a => {
        line(box, `${a.decision} · ${a.actor} · ${a.at}`, `Evidence: ${arr(a.evidence_ids).join(', ') || 'UNKNOWN'}`);
        line(box, 'SHA256 основания решения', a.basis_sha256);
      }); target.append(box);
    });
    target.append(node('h3', 'Артефакты и изменения документов'));
    if (!arr(item.artifacts).length) target.append(node('p', 'Закреплённых артефактов нет', 'note'));
    arr(item.artifacts).forEach(a => {
      const box = node('section', null, 'artifact'); box.append(node('h4', `${a.id} · ${a.role}`));
      line(box, 'Путь', a.path); line(box, 'SHA256 / bytes', `${textValue(a.sha256)} / ${textValue(a.bytes)}`);
      links(box, 'Связанные документы и контракты', a.entity_ids); patchDetail(box, a); target.append(box);
    });
    target.append(node('h3', 'Evidence'));
    if (!arr(item.evidence).length) target.append(node('p', 'Закреплённых доказательств нет', 'note'));
    arr(item.evidence).forEach(e => {
      const box = node('details', null, 'evidence'); box.append(node('summary', `${e.id} · ${e.scope} · ${e.result}`));
      line(box, 'Исполнитель / время', `${textValue(e.actor)} · ${textValue(e.at)}`); line(box, 'Окружение', e.environment);
      arr(e.subjects).forEach(s => line(box, `Artifact ${s.artifact_id}`, s.sha256));
      if (e.receipt) { line(box, 'Квитанция', e.receipt.path); line(box, 'Receipt SHA256 / bytes', `${textValue(e.receipt.sha256)} / ${textValue(e.receipt.bytes)}`); }
      target.append(box);
    });
    target.append(node('h3', 'История работы'));
    if (!arr(item.events).length) target.append(node('p', 'События не указаны', 'note'));
    arr(item.events).forEach(e => line(target, `${e.at} · ${e.actor} · ${e.kind} · ${e.id}`, `${e.summary}${arr(e.evidence_ids).length ? ' · Evidence: ' + e.evidence_ids.join(', ') : ''}`));
    raw(target, 'Полная запись работы (JSON)', item);
  }
  function detail(item) {
    const target = byId('detail'); target.replaceChildren();
    if (!item) {
      target.append(node('h2', isAtlas ? 'Детали работы' : 'Выберите объект'), node('p', isAtlas ? 'Откройте работу, чтобы увидеть цель, результат, область изменений, критерии, доказательства, блокеры и следующий шаг.' : 'Откройте документ, контракт или связь, чтобы увидеть параметры, источники и историю.', 'note'));
      if (isAtlas) {
        target.append(node('p', 'Записанный статус отражает сохранённое решение. Активность имеет отдельный срок. Этот снимок не опрашивает агентов и серверы.', 'note'));
        issues(target, snapshot.atlas.issues);
        const metadata = node('details', null, 'raw-data'); metadata.append(node('summary', 'Источники снимка и данные'));
        line(metadata, 'Дата и время снимка', snapshot.atlas.as_of); line(metadata, 'Режим', snapshot.atlas.project && snapshot.atlas.project.mode);
        line(metadata, 'Выгрузка документов', 'DOCS_INDEX.json содержит snapshot.input — проекцию документов Atlas. Исходный выпуск сохранён ниже. Полный Atlas доступен в snapshot.json.');
        raw(metadata, 'Закреплённые источники', snapshot.atlas.source_pins); raw(metadata, 'Исходный выпуск документов', snapshot.atlas.document_release);
        const b = node('button', 'Скачать полный snapshot.json'); b.dataset.snapshotDownload = 'true'; metadata.append(b); target.append(metadata);
      }
      return;
    }
    target.append(node('div', item.id, 'eyebrow'), node('h2', workDisplayTitle(presentation,item)), badges(item));
    if (item.content !== undefined) {
      [['Версия', item.version], ['Source', item.source_ref], ['Путь', item.path], ['SHA256', item.sha256], ['Байт', item.bytes], ['Время проверки UTC', item.readback_at]].forEach(([k, v]) => line(target, k, v));
      target.append(node('pre', item.content, 'document'));
    } else if (item.contract_key) {
      [['Контракт', item.contract_key], ['Версия', item.version], ['Владелец состояния', item.state_owner], ['Вход', item.input], ['Выход', item.output], ['Авторизация', item.auth], ['Использование', item.usage]].forEach(([k, v]) => line(target, k, v));
      links(target, 'Модуль', [item.module]);
      const params = node('section'); params.append(node('h3', 'Параметры'));
      if (!arr(item.parameters).length) params.append(node('p', 'Не указано'));
      arr(item.parameters).forEach(p => line(params, `${p.name} · ${p.type} · ${p.required === 'UNKNOWN' ? 'requiredness UNKNOWN' : p.required ? 'required' : 'optional'}`, p.description)); target.append(params);
      const errors = node('section'); errors.append(node('h3', 'Ошибки'));
      if (!arr(item.errors).length) errors.append(node('p', 'Не указано'));
      arr(item.errors).forEach(e => line(errors, e.code, e.meaning)); target.append(errors);
      links(target, 'Зависимости', item.dependencies); links(target, 'Документы', item.docs);
    } else {
      line(target, 'Назначение', item.purpose); line(target, 'Владелец состояния', item.state_owner);
      links(target, 'Зависимости модуля', item.dependencies); links(target, 'Документы', item.docs);
    }
    const edges = arr(snapshot.input.relations).filter(x => x.from === item.id || x.to === item.id);
    if (edges.length) { target.append(node('h3', 'Подтверждённые связи')); edges.forEach(e => links(target, `${e.from === item.id ? '→' : '←'} ${e.type}`, [e.from === item.id ? e.to : e.from])); }
    const relatedWorks = works(snapshot).filter(w => arr(w.artifacts).some(a => arr(a.entity_ids).includes(item.id)));
    if (relatedWorks.length) links(target, 'Связанные работы', relatedWorks.map(w => w.id), 'work');
    const binding = arr(snapshot.input.bindings).find(b => b.entity_id === item.id);
    if (binding && snapshot.input.matrix) {
      target.append(node('h3', 'Связи с матрицей')); links(target, 'Закреплённый снимок', [snapshot.input.matrix.doc]);
      [...arr(binding.step_ids).map(id => ['step', id]), ...arr(binding.event_ids).map(id => ['event', id])].forEach(([kind, id]) => {
        const b = node('button', `${kind === 'step' ? 'Шаг' : 'Событие'} · ${id}`, 'link'); b.dataset.matrix = `${kind}:${id}`; target.append(b);
      });
    }
    const history = arr(snapshot.input.history).filter(h => arr(h.entity_ids).includes(item.id));
    if (history.length) { target.append(node('h3', 'История объекта')); history.forEach(h => line(target, `${h.at} · ${h.id}`, h.summary)); }
  }
  function workCard(item) {
    const card = node('article', null, `card work-card${item.parent_id ? ' child-work' : ''}`); card.dataset.workId = item.id;
    card.append(node('div', item.id, 'eyebrow'));
    const b = node('button', workDisplayTitle(presentation,item), 'row-title'); b.dataset.work = item.id; card.append(b);
    if (item.parent_id) links(card, 'Дочерняя работа для', [item.parent_id], 'work');
    card.append(workBadges(item));
    line(card, 'Цель', displayText(presentation,item.id,'work.objective')); line(card, 'Ожидаемый результат', workDisplayField(item,'outcome'));
    const grid = node('div', null, 'field-grid'); line(grid, 'Назначено', arr(item.assigned_to).length ? item.assigned_to.join(', ') : item.assigned_to);
    line(grid, 'Владелец записи', item.writer); line(grid, 'Принятые критерии', criterionProgress(item));
    line(grid, 'Ранее выполняли', arr(item.derived && item.derived.completed_by).length ? item.derived.completed_by.join(', ') : 'UNKNOWN'); card.append(grid);
    if (item.blocker) {
      const blocker = node('div', null, 'blocker'); line(blocker, 'Блокер', item.blocker.reason);
      line(blocker, 'Условие / ответственный', `${textValue(item.blocker.unblock_condition)} · ${textValue(item.blocker.next_owner)}`); card.append(blocker);
    }
    if (item.result) line(card, 'Записанный результат', item.result);
    if (gapCardCaption(item)) line(card, 'Осталось', workDisplayField(item,'remaining'));
    line(card, 'Следующее действие', item.next_action ? `${textValue(item.next_action.actor)} · ${textValue(workDisplayField(item,'next_action'))}` : 'Не указано');
    const patches = arr(item.artifacts).filter(a => a.patch);
    if (patches.length) card.append(node('p', patches.map(a => `${a.id}: patch ${a.patch.state}`).join(' · '), 'note'));
    if (arr(item.derived && item.derived.issues).length) card.append(node('p', `Needs attention: ${item.derived.issues.length}. See the work item for details.`, 'attention'));
    return card;
  }
  function sourceStatus(parent, id) {
    const latest = presentation.sourceLatest.get(id), children = arr(presentation.children.get(id));
    if (children.length) {
      const accepted = children.filter(child => { const e = presentation.sourceLatest.get(child); return e && e.status === 'done' && e.accepted === true; }).length;
      parent.append(node('div', `Immediate children: ${accepted} / ${children.length} accepted in source`, 'branch-summary'));
    }
    if (!latest) { parent.append(node('div', 'Статус источника: UNKNOWN', 'note')); return; }
    const label = `${SOURCE_STATES[latest.status] || latest.status}${latest.accepted === true ? ' · accepted in source' : ''}`;
    parent.append(node('div', label, `source-state${latest.accepted === true && !children.length ? ' source-accepted' : ''}`));
    parent.append(node('div', `${latest.id} · ${latest.at}`, 'note'));
    if (latest.note) { const note = node('p', latest.note, 'cell-note'); note.title = latest.note; parent.append(note); }
  }
  function ownerAll(root = byId('owner-matrix')) {
    const result = [], stack = root ? [root] : [];
    while (stack.length) { const e = stack.pop(); result.push(e); stack.push(...Array.from(e.children || []).reverse()); }
    return result;
  }
  function ownerDate(value) {
    const d = new Date(value); return Number.isFinite(+d) ? d.toLocaleString('ru-RU', {year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Vladivostok'}) : textValue(value);
  }
  function ownerRemember() {
    for (const e of ownerAll()) {
      if (e.dataset.ownerPanel) ownerView.panels[e.dataset.ownerPanel] = Number(e.scrollTop) || 0;
      if (e.dataset.viewKey) ownerView.nested[e.dataset.viewKey] = e.open === true;
    }
  }
  function ownerSave() {
    ownerRemember(); if (!ownerView.storage || typeof window === 'undefined') return false;
    try {
      window.sessionStorage.setItem(ownerViewKey, JSON.stringify({version: 2, dataset: ownerDatasetIdentity(snapshot, presentation), release: snapshot.input.release.id, input_sha256: snapshot.input_sha256,
        expanded: [...state.expanded], filterCollapsed: [...state.filterCollapsed], details: [...ownerView.details],
        roster: ownerView.roster, panels: ownerView.panels, nested: ownerView.nested, auto: ownerView.auto, query: state.query, workState: state.workState, actor: state.actor, activeOnly: state.activeOnly,
        scrollX: window.scrollX || 0, scrollY: window.scrollY || 0})); return true;
    } catch (_) {
      ownerView.storage = false; ownerView.auto = false;
      const auto = byId('auto-refresh'); if (auto) { auto.checked = false; auto.disabled = true; }
      const status = byId('refresh-status'); if (status) status.textContent = 'Хранилище недоступно · обновление кнопкой';
      return false;
    }
  }
  function ownerRefresh(manual = false) {
    if (!isAtlas || typeof window === 'undefined' || !window.location || typeof window.location.reload !== 'function') return;
    if (!manual) {
      if (!ownerView.auto || state.tab !== 'works' || document.hidden) return;
      const focus = document.activeElement, tag = focus && String(focus.tagName).toLowerCase();
      if (['input', 'textarea', 'select'].includes(tag) || Date.now() - ownerView.lastInteraction < 5000 || (typeof window.getSelection === 'function' && String(window.getSelection()).trim())) {
        const note = byId('refresh-status'); if (note) note.textContent = 'Пауза при работе со страницей'; return;
      }
    }
    if (ownerSave() || manual) window.location.reload();
  }
  function ownerChips(ids, compact = false) {
    const box = node('span'), values = [...new Set([].concat(ids || []).filter(id => typeof id === 'string' && id && id !== 'UNKNOWN'))];
    (compact ? values.slice(0, 2) : values).forEach(id => {
      const actor = presentation.participants.get(id), a = node('a', actor && actor.label || id, 'actor-chip');
      a.href = '#actor-' + encodeURIComponent(id); a.dataset.ownerActor = id; box.append(a);
    });
    if (compact && values.length > 2) box.append(node('span', ' +' + (values.length - 2), 'more'));
    return box;
  }
  function ownerTiming(item) {
    return ownerDuration(presentation, item, Date.now(), agedActivity.get(item.id), agedSourceActivity.get(item.id));
  }
  function ownerUpdateClocks() {
    ownerAll().forEach(e => {
      if (!e.dataset.durationStep) return;
      const item = presentation.byId.get(e.dataset.durationStep); if (!item) return;
      const timing = ownerTiming(item);
      e.textContent = e.dataset.durationActor ? timing.perActor.find(x => x.actor_id === e.dataset.durationActor)?.text || '—' : timing.text;
      e.title = timing.note;
    });
  }
  function ownerObservationMap() {
    const observations = new Map(), current = ownerCurrentSummary(presentation, Date.now(), agedActivity, agedSourceActivity);
    presentation.byId.forEach((item, id) => {
      const source = displaySourceActivity(id), native = displayActivity(item);
      observations.set(id, {source, native, direct: current.current.has(id), nested: []});
    });
    observations.forEach((value, id) => {
      if (!value.direct) return;
      let p = presentation.parent.get(id); while (p !== null && p !== undefined) { observations.get(p).nested.push(id); p = presentation.parent.get(p); }
    });
    return observations;
  }
  function ownerBadge(item, observation) {
    const latest = presentation.sourceLatest.get(item.id), raw = latest ? latest.status : item.state;
    const labels = {done: ['✅', 'Выполнено', 'done'], partial: ['◐', 'Частично', 'partial'], planned: ['☑', 'Запланировано', 'planned'], waiting: ['◷', 'Ожидает', 'waiting'],
      doing: ['⏳', 'В работе', 'doing'], blocked: ['⛔', 'Заблокировано', 'waiting'], review: ['◷', 'На проверке', 'waiting'],
      PLANNED: ['☑', 'Запланировано', 'planned'], ACCEPTED: ['✅', 'Принято', 'done'], DOING: ['⏳', 'В работе', 'doing'], REVIEW: ['◷', 'На проверке', 'waiting'],
      BLOCKED: ['⛔', 'Заблокировано', 'waiting'], PAUSED: ['◷', 'Приостановлено', 'waiting'], CANCELLED: ['—', 'Отменено', 'waiting'], UNKNOWN: ['—', 'Не установлено', 'waiting']};
    // The badge is the recorded lifecycle; proof-backed activity has its own existing row label.
    const value = labels[raw] || ['—', textValue(raw), 'waiting'];
    return {icon: value[0], label: value[1], css: value[2], raw, latest};
  }
  function ownerTreeRails(depth, ancestors, following, childStem = false, after = false) {
    const rails = node('span', null, 'tree-rails'); rails.setAttribute('aria-hidden', 'true');
    const segment = (lane, cls) => { const e = node('span', null, 'tree-segment' + (cls ? ' ' + cls : '')); e.setAttribute('style', '--lane:' + lane); e.dataset.lane = String(lane); rails.append(e); };
    for (let level = 1; level < depth; level++) if (ancestors[level]) segment(level - 1, '');
    if (depth) {
      if (!after || following) segment(depth - 1, !following ? 'terminal' : '');
      if (!after) { const e = node('span', null, 'tree-elbow'); e.setAttribute('style', '--lane:' + (depth - 1)); rails.append(e); }
    }
    if (childStem) segment(depth, after ? '' : 'child-stem'); return rails;
  }
  function ownerRoster(observations) {
    const roster = node('details', null, 'roster'); roster.id = 'roster'; roster.open = ownerView.roster;
    const summary = node('summary', 'Участники и история сессий '), count = node('span', '· ' + presentation.participants.size); count.id = 'actor-count'; summary.append(count); roster.append(summary);
    const grid = node('section', null, 'actors'); grid.id = 'actors'; grid.setAttribute('aria-label', 'Участники и история сессий');
    presentation.participants.forEach(a => {
      const card = node('article', null, 'actor-card'); card.id = 'actor-' + encodeURIComponent(a.id);
      card.append(node('h2', a.label || a.id), node('div', a.role || 'Роль не указана', 'subtle'));
      if (a.session_title) card.append(node('p', a.session_title));
      const active = [...observations].flatMap(([id, o]) => {
        const source = o.direct && o.source.state === 'CURRENT' ? o.source.observations.filter(e => e.actor_id === a.id) : [];
        const work = presentation.byId.get(id), native = work && work.activity;
        return [...source, ...(work && ownerNativeCurrent(presentation, work, Date.now(), agedActivity.get(id)) && native.actor === a.id
          ? [{step_id: id, at: native.observed_at, valid_until: native.valid_until}] : [])];
      });
      const current = node('div', active.length ? active.map(e => 'Активность: ' + e.step_id + ' · наблюдалось ' + ownerDate(e.at) + ' · до ' + ownerDate(e.valid_until)).join('; ') : 'Свежая активность конкретного шага не подтверждена', 'actor-state');
      card.append(current);
      const last = presentation.actorLatest.get(a.id);
      if (last) { card.append(node('p', 'Последняя запись сессии: ' + textValue(last.state) + ' · ' + ownerDate(last.at) + ' (не подтверждение шага)', 'subtle')); if (last.note) card.append(node('p', last.note, 'subtle')); }
      if (a.history_note) card.append(node('p', a.history_note, 'subtle'));
      if (typeof a.session_url === 'string' && /^codex:\/\/threads\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(a.session_url)) {
        const link = node('a', 'Открыть чат / историю'); link.href = a.session_url; link.rel = 'noopener noreferrer'; card.append(link);
      }
      const history = node('details', null, 'actor-history'); history.dataset.viewKey = 'owner-actor-' + a.id;
      const events = eventOrder(arr(presentation.matrix && presentation.matrix.actor_events).filter(e => e && e.actor_id === a.id));
      history.append(node('summary', 'История участника · ' + events.length));
      events.forEach(e => { history.append(node('p', ownerDate(e.at) + ' · ' + textValue(e.state), 'subtle')); if (e.note) history.append(node('p', e.note)); sourceReferences(history, e.evidence); });
      const more = node('button', 'Полная карточка Atlas', 'detail-button'); more.dataset.actor = a.id; history.append(more); card.append(history); grid.append(card);
    });
    roster.append(grid); roster.addEventListener('toggle', () => { ownerView.roster = roster.open === true; }); return roster;
  }
  function ownerDetails(item, panel, observation) {
    panel.replaceChildren(); panel.className = 'panel-body'; panel.dataset.ownerPanel = item.id;
    if(hasLocalizedFields(snapshot)) line(panel,'Цель',displayText(presentation,item.id,'work.objective'));
    const step = presentation.sourceSteps.get(item.id), own = presentation.ownership.get(item.id) || {}, badge = ownerBadge(item, observation);
    if (workDisplayTitle(presentation,item)!==item.title)
      panel.append(node('p','Исходное название: '+item.title,'subtle'));
    panel.append(node('p', workDisplayTitle(presentation,item), 'title'), node('p', 'ID: ' + item.id + ' · Родитель: ' + textValue(presentation.parent.get(item.id) || 'корневой шаг') + (step && step.created_at ? ' · Создан: ' + ownerDate(step.created_at) : ''), 'subtle'));
    const chain = []; let p = presentation.parent.get(item.id); while (p !== null && p !== undefined) { chain.unshift(p); p = presentation.parent.get(p); }
    if (chain.length) panel.append(node('p', 'Родительская цепочка: ' + chain.join(' → '), 'subtle'));
    panel.append(node('p', 'Запись источника: ' + textValue(badge.raw) + ' · ' + (observation.direct ? 'свежее наблюдение этого шага' : observation.nested.length ? 'наблюдение на вложенных шагах: ' + observation.nested.join(', ') : 'текущая активность отдельно не подтверждена'), 'subtle'));
    const meta = node('div', null, 'panel-meta');
    [['executor_ids', 'Назначены по журналу'], ['contributor_ids', 'Сделали / участвовали'], ['reviewer_ids', 'Проверка'], ['history_ids', 'Где история'], ['coordinator_id', 'Координатор']].forEach(([key, title]) => {
      const col = node('div'); col.append(node('div', title, 'who-label'), [].concat(own[key] || []).length ? ownerChips(own[key]) : node('span', 'Не указаны', 'subtle')); meta.append(col);
    }); panel.append(meta);
    const time = ownerTiming(item), timing = node('div', null, 'timing-panel'), timeLine = node('p', 'Подтверждённый источник времени: '), totalClock = node('span', time.text, 'duration');
    totalClock.dataset.durationStep = item.id; totalClock.title = time.note; timeLine.append(totalClock); timing.append(timeLine);
    time.perActor.forEach(value => { const row = node('p'), clock = node('span', value.text, 'duration'); clock.dataset.durationStep = item.id; clock.dataset.durationActor = value.actor_id; clock.title = time.note; row.append(ownerChips([value.actor_id]), node('span', ' · '), clock); timing.append(row); });
    timing.append(node('p', time.note + '; времена родителей и параллельных шагов не суммируются.', 'subtle')); if (time.evidence) raw(timing, 'Исходное подтверждение времени', time.evidence); panel.append(timing);
    observation.source.observations.forEach(e => panel.append(node('p', e.actor_id + ' → ' + e.step_id + ' · наблюдалось ' + ownerDate(e.at) + ' · до ' + ownerDate(e.valid_until), 'activity-note')));
    const savedObservations = arr(presentation.observationMap.get(item.id));
    if (savedObservations.length) {
      const saved = node('details'); saved.dataset.viewKey = 'owner-observations-' + item.id;
      saved.append(node('summary', 'Сохранённые наблюдения шага · ' + savedObservations.length));
      saved.append(node('p', 'История наблюдений источника. Нахождение записи не назначает исполнителя и не подтверждает текущую активность или приёмку. Оценка шага: Source ' + observation.source.state + ' · Atlas ' + observation.native + '.', 'subtle'));
      savedObservations.forEach(e => {
        saved.append(node('p', textValue(e.actor_id) + ' → ' + e.step_id + ' · в источнике: ' + textValue(e.state) + ' · ' + textValue(e.at) + ' · до ' + textValue(e.valid_until), 'subtle'));
        if (e.observation) saved.append(node('p', textValue(e.observation)));
        if (e.note) saved.append(node('p', textValue(e.note)));
        sourceReferences(saved, e.evidence); raw(saved, 'Полная исходная запись наблюдения', e);
      }); panel.append(saved);
    }
    if (step && step.scope_note) panel.append(node('p', displayText(presentation,item.id,'work.scope_note')));
    if (step && step.source_definition) { const definition = node('details'); definition.dataset.viewKey = 'owner-definition-' + item.id; definition.append(node('summary', 'Исходное определение шага'), node('pre', typeof step.source_definition === 'string' ? step.source_definition : JSON.stringify(step.source_definition, null, 2))); panel.append(definition); }
    panel.append(node('p', 'Ниже сохранены исторические записи. Они не являются новым подтверждением активности или приёмкой Atlas.', 'subtle'));
    const list = node('ol', null, 'history');
    arr(presentation.eventMap.get(item.id)).forEach(event => {
      const li = node('li'); li.append(node('strong', textValue(event.status) + ' · запись', 'badge historical-status'), node('p', ownerDate(event.at), 'subtle'), node('p', event.note || 'Без заметки'), node('div', 'Событие: ' + event.id, 'id'));
      SOURCE_ROLES.forEach(key => { if (Object.prototype.hasOwnProperty.call(event, key)) li.append(node('div', {executor_ids: 'Исполнители', contributor_ids: 'Участники результата', reviewer_ids: 'Проверка', history_ids: 'История сессий', coordinator_id: 'Координатор'}[key] + ':', 'who-label'), ownerChips(event[key])); });
      if (Object.prototype.hasOwnProperty.call(event, 'accepted')) li.append(node('p', 'Приёмка в исходной записи: ' + String(event.accepted), 'subtle'));
      sourceReferences(li, event.evidence); raw(li, 'Полная исходная запись', event); list.append(li);
    }); panel.append(list);
    const records = node('details'); records.dataset.viewKey = 'owner-atlas-' + item.id; records.append(node('summary', 'Atlas: документы, контракты, критерии, доказательства и полный JSON'));
    const content = node('div'); workDetail(item, content); records.append(content); panel.append(records);
  }
  function countOwnerStatuses(s, model = buildPresentation(s)) {
    const status = {done:0, doing:0, waiting:0, blocked:0, partial:0, review:0, planned:0, paused:0, cancelled:0, unknown:0};
    const declared = model.matrix ? [...model.sourceSteps.keys()] : [...model.byId.keys()];
    let acceptedInSource = 0;
    for (const id of declared) {
      const latest=model.sourceLatest.get(id);
      const raw=String(latest?.status || model.byId.get(id)?.state || 'UNKNOWN').toLowerCase();
      const group=({
        accepted:'done',completed:'done',complete:'done',done:'done',
        doing:'doing',started:'doing',in_progress:'doing',
        waiting:'waiting',queued:'waiting',pending:'waiting',
        blocked:'blocked',
        partial:'partial',partially_completed:'partial',
        review:'review',verifying:'review',
        planned:'planned',not_started:'planned',
        paused:'paused',cancelled:'cancelled',canceled:'cancelled'
      })[raw] || 'unknown';
      status[group]++;
      if (latest?.status === 'done' && latest.accepted === true) acceptedInSource++;
    }
    return {schema:'atlas.matrix-status-counts/v1',basis:model.matrix?'EXACT_SOURCE_STEPS':'ATLAS_WORKS_FALLBACK',
      source_revision:model.matrix?.revision??'UNKNOWN',
      total:declared.length, statuses:status, accepted_in_source:acceptedInSource,
      atlas_only: model.matrix ? [...model.byId.keys()].filter(id=>!model.sourceSteps.has(id)).length : 0,
      freshness:'DATED_SNAPSHOT_NOT_LIVE'};
  }
  function atlasFitOwnerColumns(root){
    if(typeof requestAnimationFrame!=='function')return;
    requestAnimationFrame(()=>{
      const table=root.querySelector('table'),wrap=table?.parentElement;if(!table||!wrap?.clientWidth)return;
      const canvas=document.createElement('canvas'),ctx=canvas.getContext?.('2d');if(!ctx||typeof getComputedStyle!=='function')return;
      const measure=(text,e)=>{const cs=getComputedStyle(e);ctx.font=cs.font||`${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;return ctx.measureText(text).width};
      let work=240,status=85,actor=105;
      for(const row of table.querySelectorAll('tr.work-row')){
        const cells=row.children,title=cells[0]?.querySelector('.title');if(title)work=Math.max(work,measure(title.textContent,title)+60);
        const holder=cells[1]?.querySelector('.atlas-status-distribution');if(holder){let n=0;const badges=[...holder.children];for(const b of badges){const cs=getComputedStyle(b);n+=[...b.children].reduce((v,c)=>v+measure(c.textContent,c),0)+parseFloat(cs.paddingLeft)+parseFloat(cs.paddingRight)+9}status=Math.max(status,n+Math.max(0,badges.length-1)*4+20)}
        if(cells[2])for(const chip of cells[2].querySelectorAll('a, .actor-chip, .duration'))actor=Math.max(actor,measure(chip.textContent,chip)+20);
      }
      actor=Math.min(actor,220);const width=wrap.clientWidth,sizes=[work,status,actor],min=[Math.min(240,width*.5),65,105];let lack=sizes.reduce((a,b)=>a+b,0)-width;
      if(lack<0)sizes[0]-=lack;
      else {for(const i of [0,2,1]){const n=Math.min(lack,Math.max(0,sizes[i]-min[i]));sizes[i]-=n;lack-=n}if(lack>0){const ratio=width/sizes.reduce((a,b)=>a+b,0);for(let i=0;i<3;i++)sizes[i]*=ratio}}
      const cols=table.querySelectorAll('col');sizes.forEach((n,i)=>cols[i]?.style.setProperty('width',n+'px','important'));
    });
  }
  function ownerMatrix(parent) {
    state.agedActivity = agedActivity; state.agedSourceActivity = agedSourceActivity;
    const result = roadmapRows(snapshot, state), observations = ownerObservationMap(), matrix = presentation.matrix;
    const journalCount = [...presentation.byId.values()].filter(item => journalDoing(presentation, item)).length;
    const counts=countOwnerStatuses(snapshot,presentation);
    const root = node('div'); root.id = 'owner-matrix';
    const projectStrip=node('div',null,'atlas-project-strip');const title=node('h1',projectDisplayTitle(snapshot));title.id='project';projectStrip.append(title);root.append(projectStrip);
    const archive=node('details',null,'atlas-source-info');archive.append(node('summary','О снимке и данные'));archive.append(ownerRoster(observations));
    const summary=node('p',matrix?.snapshot_summary||displayText(presentation,snapshot.atlas.project.id,'project.objective')||'', 'subtle');summary.id='snapshot-summary';summary.setAttribute('aria-live','polite');archive.append(summary);
    archive.append(node('p','Редакция '+textValue(matrix?.revision)+' · '+ownerDate(snapshot.atlas.as_of)+' · '+snapshot.input.release.id,'meta'));
    const legend = node('div', null, 'legend'); legend.setAttribute('aria-label', 'Легенда статусов');
    const indicators = [
      ['done','✅','Выполнено'],['doing','⏳','В работе · по журналу'],['waiting','⌛','Ожидает'],
      ['blocked','⛔','Заблокировано'],['partial','◐','Частично'],['review','🔎','На проверке'],
      ['planned','📋','Запланировано'],['paused','⏸','Приостановлено'],
      ['cancelled','⏹','Отменено'],['unknown','❔','Не определено']
    ];
    indicators.forEach(([kind, emoji, label]) => {
      if (['paused','cancelled','unknown'].includes(kind) && !counts.statuses[kind]) return;
      const display=node('button',null,'atlas-status-copy '+kind);display.append(node('span',emoji),node('strong',String(counts.statuses[kind])));display.dataset.atlasStatus=kind;display.dataset.atlasScope='ALL';display.title='Скопировать ТЗ: '+label+' · '+counts.statuses[kind];display.setAttribute('aria-label',display.title);display.dataset.matrixCount=kind;
      legend.append(display);
    });
    const sourceTotal=node('span','Всего: ' + counts.total +
      (counts.atlas_only?' · служебных Atlas отдельно: ' + counts.atlas_only:'') +
      (counts.accepted_in_source?' · принято по исходному журналу: ' + counts.accepted_in_source:''),'subtle');
    sourceTotal.id='matrix-total';archive.append(sourceTotal);projectStrip.append(legend);
    const controls = node('div', null, 'toolbar');
    const search = node('input'); search.id = 'matrix-search'; search.type = 'search'; search.value = state.query; search.setAttribute('aria-label', 'Поиск по шагам, заметкам, наблюдениям и истории'); search.setAttribute('placeholder', 'Найти шаг, заметку, наблюдение…');
    search.addEventListener('input', () => { state.query = search.value; state.filterCollapsed.clear(); render(); }); controls.append(search);
    const filter = node('select'); filter.id = 'filter'; filter.setAttribute('aria-label', 'Фильтр статуса');
    [['all', 'Все статусы'], ['journal:doing', '⏳ В работе · по журналу'], ['active', 'Подтверждённая активность'], ...(matrix ? [['source:done', '✅ Выполнено (' + counts.statuses.done + ')'], ['source:doing', '⏳ В работе (' + counts.statuses.doing + ')'], ['source:waiting', '⌛ Ожидает (' + counts.statuses.waiting + ')'], ['source:blocked', '⛔ Заблокировано (' + counts.statuses.blocked + ')'], ['source:partial', '◐ Частично (' + counts.statuses.partial + ')'], ['source:review', '🔎 На проверке (' + counts.statuses.review + ')'], ['source:planned', '📋 Запланировано (' + counts.statuses.planned + ')']] : []), ...Object.keys(STATES).map(key => [key, 'Atlas · ' + STATES[key]])].forEach(([value, label]) => { const o = node('option', label); o.value = value; filter.append(o); });
    filter.value = state.activeOnly ? 'active' : state.workState; filter.addEventListener('change', () => { state.activeOnly = filter.value === 'active'; state.workState = state.activeOnly ? 'all' : filter.value; state.filterCollapsed.clear(); render(); }); controls.append(filter);
    const actor = node('select'); actor.id = 'actor-filter'; actor.setAttribute('aria-label', 'Фильтр участника');
    const lookupActors = new Map([...presentation.participants.values()].map(a => [a.id, a.label || a.id]));
    presentation.observationMap.forEach((_, id) => observationActors(presentation, id).forEach(actorId => { if (!lookupActors.has(actorId)) lookupActors.set(actorId, actorId + ' · только наблюдение'); }));
    [['', 'Все участники'], ...lookupActors].forEach(([value, label]) => { const o = node('option', label); o.value = value; actor.append(o); }); actor.value = state.actor;
    actor.addEventListener('change', () => { state.actor = actor.value; state.filterCollapsed.clear(); render(); }); controls.append(actor);
    const activity = ownerCurrentSummary(presentation, Date.now(), agedActivity, agedSourceActivity);
    const active = node('button', 'Сейчас в работе · шагов: ' + activity.steps + ' · исполнителей: ' + activity.actors); active.id = 'active-now'; active.dataset.ownerActive = 'true'; active.dataset.currentSteps = String(activity.steps); active.dataset.currentActors = String(activity.actors); active.setAttribute('aria-pressed', String(state.activeOnly)); controls.append(active);
    const all = node('button', 'Все шаги'); all.id = 'all-steps'; all.dataset.ownerRecover = 'all'; controls.append(all);
    const freshness = node('p', (activity.steps ? 'Подтверждены только перечисленные конечные шаги.' : 'Текущее выполнение неизвестно: свежих подтверждений нет.') +
      (activity.latest ? ' Последнее сохранённое наблюдение: ' + ownerDate(activity.latest.at) + ' · ' + activity.latest.step_id + '.' : ' Сохранённых наблюдений конечных шагов нет.') +
      ' Покрытие текущих сессий неполное; ноль подтверждений не означает отсутствие работы.', 'activity-summary'); freshness.id = 'activity-summary'; freshness.setAttribute('aria-live', 'polite');
    [['expand', 'Раскрыть всё', 'expandAll'], ['collapse', 'Свернуть всё', 'collapseAll'], ['refresh', '↻ Обновить', 'ownerRefresh']].forEach(([id, title, action]) => { const b = node('button', title); b.id = id; b.dataset[action] = 'true'; controls.append(b); });
    const refreshLabel = node('label', null, 'refresh-control'), auto = node('input'); auto.id = 'auto-refresh'; auto.type = 'checkbox'; auto.checked = ownerView.auto; auto.disabled = !ownerView.storage; auto.title = 'Перечитать этот URL: стабильный вход обновляется после публикации, ссылка на сохранённый release остаётся неизменной';
    auto.addEventListener('change', () => { ownerView.auto = auto.checked === true; ownerSave(); const s = byId('refresh-status'); if (s) s.textContent = !ownerView.storage ? 'Хранилище недоступно · обновление кнопкой' : ownerView.auto ? 'Вид сохраняется' : 'Автообновление выключено'; }); refreshLabel.append(auto, node('span', 'Авто · 30 с')); controls.append(refreshLabel);
    const refreshStatus = node('span', ownerView.releaseChanged ? 'Новый снимок · вид восстановлен по стабильным ID' : '', 'refresh-status'); refreshStatus.id = 'refresh-status'; refreshStatus.setAttribute('aria-live', 'polite'); controls.append(refreshStatus);
    const download = node('button', 'Скачать JSON'); download.id = 'export'; download.dataset[matrix ? 'matrixDownload' : 'snapshotDownload'] = 'true'; controls.append(download);
    const count = node('span', state.query || state.actor || state.activeOnly || state.workState !== 'all' ? 'Совпадений: ' + result.matches + ' · видно ' + result.rows.length + ' с предками' : 'Видно ' + result.rows.length + ' из ' + result.total, 'counter'); count.id = 'count'; count.setAttribute('aria-live', 'polite'); controls.append(count);archive.append(controls,freshness);
    const wrap = node('div', null, 'table-wrap'), table = node('table'), colgroup = node('colgroup'); table.setAttribute('aria-label', 'Матрица работ');
    ['step','status','who'].forEach(name => colgroup.append(node('col', null, 'col-' + name))); table.append(colgroup);
    const thead=node('thead'),headings=node('tr'),workHead=node('th'),statusHead=node('th'),actorHead=node('th');
    const headerTools=node('div',null,'atlas-header-tools');headerTools.append(search);search.placeholder='Найти работу…';
    const tree=node('button','↕','atlas-head-icon');tree.title='Раскрыть / свернуть всё';tree.setAttribute('aria-label',tree.title);tree.addEventListener('click',()=>{const ids=[...presentation.children].filter(([id,kids])=>id&&kids.length).map(([id])=>id);const collapse=ids.every(id=>state.expanded.has(id));state.expanded=collapse?new Set():new Set(ids);state.filterCollapsed.clear();render()});headerTools.append(tree);
    const common=node('button','⧉','atlas-head-icon');common.dataset.atlasUnfinishedAll='true';common.title='Копировать все невыполненные работы';common.setAttribute('aria-label',common.title);headerTools.append(common);workHead.append(headerTools);statusHead.append(filter);actorHead.append(actor);[workHead,statusHead,actorHead].forEach(th=>{th.setAttribute('scope','col');headings.append(th)});thead.append(headings);table.append(thead);
    const body = node('tbody'); body.id = 'rows';
    const branchPalette = ['69,128,164','123,106,161','61,142,121',
      '179,124,71','101,126,167','163,106,139'];
    const branchTone = id => {
      // Stable by top-level work ID, independent of filter, sorting or status.
      let hash = 0;
      for (const c of String(id)) hash = (hash * 31 + c.codePointAt(0)) >>> 0;
      return branchPalette[hash % branchPalette.length];
    };
    const visible = new Set(result.rows.map(row => row.id)), siblingMap = new Map();
    presentation.children.forEach((ids, id) => siblingMap.set(id, ids.filter(child => visible.has(child))));
    const following = id => { const ids = siblingMap.get(presentation.parent.get(id)) || []; return ids.indexOf(id) < ids.length - 1; };
    result.rows.forEach(row => {
      const item = row.item, o = observations.get(row.id), badge = ownerBadge(item, o), kids = siblingMap.get(row.id) || [], chain = []; let p = presentation.parent.get(row.id);
      while (p !== null && p !== undefined) { chain.unshift(p); p = presentation.parent.get(p); }
      const ancestors = chain.map(following), hasChildren = row.children.length > 0, open = !!kids.length, tr = node('tr', null, ['step-row', 'work-row', 'depth-' + Math.min(row.depth, 3), row.depth > 3 ? 'depth-deep' : '', row.depth ? 'child-work' : '', hasChildren ? 'stage' : '', row.context_only ? 'context' : '', row.metadata_only ? 'metadata-work' : '', o.direct ? 'current ' + (hasChildren ? 'active-parent' : 'active-leaf') : o.nested.length ? 'current active-branch' : ''].filter(Boolean).join(' '));
      tr.dataset.stepId = row.id; tr.dataset.workId = row.id; tr.dataset.sourceActivity = o.source.state; tr.dataset.nativeActivity = o.native;
      const branchRoot = chain[0] || row.id, branchRgb = branchTone(branchRoot);
      tr.dataset.branchRoot = branchRoot;
      tr.tabIndex = 0; tr.setAttribute('style', '--tree-depth:' + row.depth + ';--branch-rgb:' + branchRgb); tr.setAttribute('data-depth', row.depth); tr.setAttribute('aria-label', workDisplayTitle(presentation,item) + '. ' + (hasChildren ? 'Раскрыть или свернуть ветку' : 'Открыть детали'));
      const filtered = state.query || state.actor || state.activeOnly || state.workState !== 'all', isOpen = filtered ? !state.filterCollapsed.has(row.id) : state.expanded.has(row.id);
      if (hasChildren) tr.setAttribute('aria-expanded', String(isOpen));
      const cell = node('td', null, 'step-cell'), line = node('div', null, 'step-line'); cell.append(ownerTreeRails(row.depth, ancestors, following(row.id), open));
      if (hasChildren) { const b = node('button', isOpen ? '▾' : '▸', 'toggle'); b.dataset.toggle = row.id; b.setAttribute('aria-label', (isOpen ? 'Свернуть' : 'Раскрыть') + ' ветку: ' + workDisplayTitle(presentation,item)); b.setAttribute('aria-expanded', String(isOpen)); line.append(b); }
      else line.append(node('span', '', 'spacer'));
      const heading = node('div', null, 'heading'), title = node(!matrix && !hasChildren ? 'button' : 'div', workDisplayTitle(presentation,item), 'title'); if (!matrix && !hasChildren) title.dataset.work = item.id; title.title = workDisplayTitle(presentation,item); heading.append(title);
      if (o.direct || o.nested.length) heading.append(node('span', o.direct ? 'Работа здесь' : 'Работа внутри', 'work-location'));
      const identity = node('div', null, 'id'); identity.append(node('span', row.depth === 0 ? 'КОРЕНЬ' : row.depth === 1 ? 'БЛОК' : row.depth === 2 ? 'ШАГ' : 'ПОДШАГ ' + (row.depth + 1), 'level-chip'), node('span', row.id + (row.context_only ? ' · контекст' : '') + (row.metadata_only ? ' · Atlas metadata' : '')));
      if (hasChildren) identity.append(node('span', '· ' + row.children.length + ' вложенных', 'branch-count')); heading.append(identity);
      if (snapshot.atlas.localized_fields) for(const field of ['objective','scope_note']){const value=displayField(presentation,row.id,'work.'+field);if(value.value!==undefined&&value.status!=='ORIGINAL'){const note=node('p',displayText(presentation,row.id,'work.'+field),'cell-note');note.dataset.displayField=field;note.title=value.status;heading.append(note);}}
      if (!matrix) {
        const nativeSummary = node('details', null, 'native-row-summary'); nativeSummary.append(node('summary', 'Результат / следующий шаг'));
        if (item.parent_id) links(nativeSummary, 'Дочерняя работа для', [item.parent_id], 'work');
        nativeSummary.append(node('p', workDisplayField(item,'outcome') || displayText(presentation,item.id,'work.objective') || ''), node('p', 'Record owner: ' + textValue(item.writer)), node('p', 'Accepted criteria ' + criterionProgress(item)));
        if (item.result) nativeSummary.append(node('p', item.result));
        if (item.blocker) nativeSummary.append(node('p', item.blocker.reason), node('p', item.blocker.unblock_condition));
        if (item.next_action) nativeSummary.append(node('p', textValue(item.next_action.actor) + ' · ' + textValue(workDisplayField(item,'next_action')))); heading.append(nativeSummary);
      }
      line.append(heading); cell.append(line); tr.append(cell);
      const status=node('td'),dist=atlasStatusDistribution(snapshot,row.id);const chips=node('div',null,'atlas-status-distribution');
      for(const [kind,ids]of dist){const def=indicators.find(x=>x[0]===kind)||['unknown','❔','Не определено'];const chip=node('button',null,'atlas-status-copy '+kind);chip.append(node('span',def[1]),node('strong',String(ids.length)));chip.dataset.atlasStatus=kind;chip.dataset.atlasScope=row.id;chip.title='Скопировать ТЗ: '+def[2]+' · '+ids.length+' · '+row.id;chip.setAttribute('aria-label',chip.title);chips.append(chip)}status.append(chips);tr.append(status);
      const own = presentation.ownership.get(row.id) || {}, who = node('td'), sourceActors = o.direct ? activity.current.get(row.id) || [] : o.nested.flatMap(id => activity.current.get(id) || []);
      const performers = sourceActors.length ? sourceActors : badge.raw === 'done' && arr(own.contributor_ids).length ? own.contributor_ids : arr(own.executor_ids).length ? own.executor_ids : [].concat(item.assigned_to || []).filter(id => id !== 'UNKNOWN');
      who.append(node('div', o.direct ? 'Работа здесь' : o.nested.length ? 'Работа внутри' : 'По журналу', 'owner-role-label'));
      who.append(performers.length ? ownerChips(performers, !o.direct && !o.nested.length) : node('div', 'Не назначены', 'subtle'));
      if (o.direct || o.nested.length) { const scopes = o.direct ? [row.id] : o.nested; const brief = node('span', scopes.slice(0, 2).join(', ') + ' · наблюдалось' + (scopes.length > 2 ? ' +' + (scopes.length - 2) : ''), 'scope-summary'); brief.title = o.source.reason; who.append(brief); } tr.append(who);
      const timing=ownerTiming(item),clock=node('div',timing.text,'duration');clock.dataset.durationStep=row.id;clock.title=timing.note;who.append(clock);
      const action = e => { if (e.target !== tr && ['button', 'a', 'input', 'select', 'textarea', 'summary'].some(tag => e.target.closest && e.target.closest(tag))) return; if (hasChildren) { const set = filtered ? state.filterCollapsed : state.expanded; set.has(row.id) ? set.delete(row.id) : set.add(row.id); } else { ownerView.details.has(row.id) ? ownerView.details.delete(row.id) : ownerView.details.add(row.id); } ownerView.focusRow = row.id; render(); };
      tr.addEventListener('click', action); tr.addEventListener('keydown', e => { if (e.target === tr && ['Enter', ' '].includes(e.key)) { if (e.preventDefault) e.preventDefault(); action(e); } }); body.append(tr);
      if (ownerView.details.has(row.id)) {
        const detailRow = node('tr', null, 'details-row'), detailCell = node('td'); detailRow.dataset.detailFor = row.id; detailRow.dataset.branchRoot = branchRoot;
        detailRow.setAttribute('style', '--tree-depth:' + row.depth + ';--branch-rgb:' + branchRgb); detailCell.colSpan = 3;
        const panel = state.selectionKind === 'work' && state.selection === row.id ? ownerPane : node('div'); if (panel !== ownerPane) panel.id = 'owner-details-' + row.id;
        ownerDetails(item, panel, o); detailCell.append(ownerTreeRails(row.depth, ancestors, following(row.id), open, true), panel); detailRow.append(detailCell); body.append(detailRow);
      }
    });
    const maxDepth = Math.max(1, ...result.rows.map(row => row.depth)); body.setAttribute('style', '--tree-unit:min(16px, calc(12vw / ' + maxDepth + '), calc(120px / ' + maxDepth + '))'); table.append(body); wrap.append(table);
    const empty = node('div', null, 'empty'); empty.id = 'empty'; empty.hidden = result.rows.some(row => !row.context_only);
    const emptyReason = !result.total ? 'В этом снимке нет записей работ.' : result.matches ? 'Найденные шаги скрыты свёрнутыми ветками.' : state.activeOnly
      ? 'В выбранном виде нет подходящих свежих подтверждений активности. Наблюдения могут отсутствовать, истечь или не пройти проверку; поиск и фильтры тоже ограничивают список.'
      : state.workState === 'journal:doing' && !journalCount ? 'В этом снимке нет работ со статусом doing в журнале источника или DOING в Atlas.' : 'Подходящих шагов нет: действуют выбранные поиск и фильтры.';
    empty.append(node('p', emptyReason), node('p', (journalCount ? 'По журналу в работе: ' + journalCount + '. ' : 'Работы со статусом doing/DOING в этом снимке не записаны. ') + 'Это отображение сохранённых данных, не проверка текущих сессий.', 'subtle'));
    if (result.total) { const recover = node('button', journalCount ? 'Показать работы по журналу (' + journalCount + ')' : 'Показать все работы'); recover.dataset.ownerRecover = journalCount ? 'journal' : 'all'; empty.append(recover); }
    wrap.append(empty); root.append(wrap);
    archive.append(node('p', 'Нажмите строку со стрелкой, чтобы раскрыть или свернуть один уровень. Конечный шаг и кнопка «Детали» открывают полную запись под строкой: заметки, координатора, участников, доказательства и историю. Поиск и фильтры показывают совпадения с предками. «В работе» — записанное состояние; свежая активность подтверждается отдельно. «Работа внутри» указывает на наблюдение вложенного шага, а не активность родителя. Приёмка Atlas и записи исходного журнала сохраняются отдельно. Время без подтверждённого значения — «—». Часовой пояс: Asia/Vladivostok. Это сохранённый снимок, не монитор сессий. Обновление перечитывает этот URL: стабильный вход получает опубликованный текущий снимок, ссылка на release и скачанная копия сохраняют свою версию. Автообновление по умолчанию выключено и ждёт при вводе или выделении текста.', 'notice'));
    const extra = node('details', null, 'matrix-extra'); extra.dataset.viewKey = 'owner-extra'; extra.append(node('summary', 'Данные Atlas, покрытие и дополнительные выгрузки')); coverage(extra); issues(extra, presentation.issues);
    const complete = node('button', 'Скачать полный snapshot.json'); complete.dataset.snapshotDownload = 'true'; extra.append(complete);archive.append(extra);root.append(archive);
    if (state.error) root.append(node('p', state.error, 'attention'));
    parent.append(root);atlasFitOwnerColumns(root);
    for (const e of ownerAll(root)) { if (e.dataset.viewKey) e.open = ownerView.nested[e.dataset.viewKey] === true; if (e.dataset.ownerPanel) e.scrollTop = ownerView.panels[e.dataset.ownerPanel] || 0; }
    byId('summary').textContent = result.matches + ' work items match of ' + result.total + ' · ' + result.rows.length + ' rows visible with ancestor context';
  }
  function roadmap(parent) {
    state.agedActivity = agedActivity; state.agedSourceActivity = agedSourceActivity;
    const result = roadmapRows(snapshot, state), controls = node('div', null, 'roadmap-controls');
    [['expandAll', 'Expand all'], ['collapseAll', 'Collapse all'], ['activeOnly', state.activeOnly ? 'Show all work' : 'Current observations']].forEach(([action, label]) => {
      const b = node('button', label); b.dataset[action] = 'true'; if (action === 'activeOnly') b.setAttribute('aria-pressed', String(state.activeOnly)); controls.append(b);
    });
    const complete = node('button', 'Скачать полный снимок'); complete.dataset.snapshotDownload = 'true'; controls.append(complete);
    if (presentation.matrix) { const b = node('button', 'Скачать точную матрицу источника'); b.dataset.matrixDownload = 'true'; controls.append(b); }
    parent.append(controls);
    parent.append(node('p', 'Записанные результаты, наблюдения источника и приёмка Atlas — разные факты. Родители суммируют дочерние работы, но не наследуют их приёмку. Поиск сохраняет совпавшие работы и их предков.', 'note roadmap-legend'));
    if (state.error) parent.append(node('p', state.error, 'attention'));
    const wrap = node('div', null, 'roadmap-scroll'), table = node('table', null, 'roadmap-table'); table.setAttribute('aria-label', 'Дерево работ проекта');
    const head = node('thead'), headings = node('tr');
    ['Работа / уровень', 'Записанный результат', 'Наблюдение активности', 'Participants', 'History', 'Зависимости / следующий шаг'].forEach(title => { const th = node('th', title); th.setAttribute('scope', 'col'); headings.append(th); });
    head.append(headings); table.append(head); const body = node('tbody');
    result.rows.forEach(row => {
      const item = row.item, tr = node('tr', null, `work-row${row.depth ? ' child-work' : ''}${row.context_only ? ' context-row' : ''}${row.metadata_only ? ' metadata-work' : ''}`);
      tr.dataset.workId = item.id; tr.setAttribute('data-depth', row.depth); tr.setAttribute('style', `--depth:${row.depth}`);
      if (state.selection === item.id && state.selectionKind === 'work') tr.setAttribute('aria-selected', 'true');
      const name = node('td', null, 'work-name'), indent = node('div', null, 'work-indent');
      if (row.children.length) {
        const filtered = state.query || state.actor || state.activeOnly || state.workState !== 'all';
        const open = filtered ? !state.filterCollapsed.has(item.id) : state.expanded.has(item.id);
        const b = node('button', open ? '▾' : '▸', 'tree-toggle'); b.dataset.toggle = item.id; b.setAttribute('aria-expanded', String(open)); b.setAttribute('aria-label', `Expand or collapse ${item.id}`); indent.append(b);
      }
      const label = node('div'); label.append(node('div', `${item.id}${row.metadata_only ? ' · Atlas metadata' : ''}${row.context_only ? ' · ancestor context' : ''}`, 'eyebrow'));
      const title = node('button', workDisplayTitle(presentation,item), 'row-title'); title.dataset.work = item.id; label.append(title);
      const sourceStep = presentation.sourceSteps.get(item.id);
      if (sourceStep && sourceStep.scope_note) { const note = node('p', displayText(presentation,item.id,'work.scope_note'), 'cell-note'); note.title = displayText(presentation,item.id,'work.scope_note'); label.append(note); }
      else if (item.outcome) label.append(node('p', workDisplayField(item,'outcome'), 'cell-note'));
      if (item.parent_id) links(label, 'Дочерняя работа для', [item.parent_id], 'work');
      indent.append(label); name.append(indent); tr.append(name);
      const resultCell = node('td'); if (presentation.matrix && sourceStep) sourceStatus(resultCell, item.id);
      else if (item.result) resultCell.append(node('p', item.result, 'cell-note'));
      resultCell.append(node('div', `Recorded state: ${textValue(item.state)} · Atlas`, 'note'), node('div', `Accepted criteria ${criterionProgress(item)}`, 'note')); tr.append(resultCell);
      const activityCell = node('td'), active = displayActivity(item);
      activityCell.append(node('div', `Activity: ${active} · Atlas`, `badge activity-${active.toLowerCase()}`));
      if (sourceStep) {
        const observed = displaySourceActivity(item.id);
        activityCell.append(node('div', `Source observation: ${observed.state}`, `source-observation source-observation-${observed.state.toLowerCase()}`));
        observed.observations.forEach(e => { actorChips(activityCell, e.actor_id); activityCell.append(node('div', `${e.at} → ${textValue(e.valid_until)}`, 'note')); });
        activityCell.append(node('p', observed.reason, 'cell-note note'));
      }
      tr.append(activityCell);
      const ownershipCell = node('td'), own = presentation.ownership.get(item.id);
      if (sourceStep) { actorChips(ownershipCell, own.executor_ids, 'Исполнение'); actorChips(ownershipCell, own.reviewer_ids, 'Проверка'); actorChips(ownershipCell, own.contributor_ids, 'Участие'); actorChips(ownershipCell, own.coordinator_id, 'Координация'); }
      else actorChips(ownershipCell, [].concat(item.assigned_to || []), 'Назначено');
      ownershipCell.append(node('div', `Record owner: ${textValue(item.writer)}`, 'note')); tr.append(ownershipCell);
      const eventCell = node('td'), events = arr(presentation.eventMap.get(item.id));
      const history = node('button', `${events.length} source / ${arr(item.events).length} Atlas`, 'link'); history.dataset.work = item.id; eventCell.append(history);
      const latest = presentation.sourceLatest.get(item.id) || arr(item.events).slice(-1)[0]; if (latest) eventCell.append(node('div', latest.at, 'note'));
      const exact = node('a', 'Прямая ссылка', 'direct-link'); exact.href = routeFor('work', item.id); eventCell.append(exact); tr.append(eventCell);
      const next = node('td');
      if (arr(item.depends_on).length) links(next, 'Зависит от', item.depends_on, 'work'); else next.append(node('div', 'Зависимости не указаны', 'note'));
      const ids = [...new Set(arr(item.artifacts).flatMap(a => arr(a.entity_ids)))];
      if (ids.length) { const b = node('button', `${ids.length} linked catalog / document records`, 'link'); b.dataset.work = item.id; next.append(b); }
      if (item.blocker) {
        const box = node('div', null, 'blocker'); box.append(node('p', item.blocker.reason));
        if (item.blocker.unblock_condition) box.append(node('p', item.blocker.unblock_condition));
        if (item.blocker.next_owner) actorChips(box, item.blocker.next_owner, 'Снять блокировку'); next.append(box);
      }
      if (item.next_action) next.append(node('p', `${textValue(item.next_action.actor)} · ${textValue(workDisplayField(item,'next_action'))}`, 'cell-note'));
      else next.append(node('div', 'Следующий шаг не указан', 'note'));
      tr.append(next); body.append(tr);
    });
    table.append(body); wrap.append(table); parent.append(wrap);
    if (!result.rows.length) parent.append(node('p', 'Ничего не найдено. Сбросьте фильтры, чтобы восстановить дерево.', 'empty'));
    byId('summary').textContent = `${result.matches} work items match of ${result.total} · ${result.rows.length} rows visible with ancestor context${presentation.matrix ? ` · ${presentation.matrix.steps.length} source steps; Atlas metadata shown separately` : ''}`;
  }
  function participantDetail(id, target = byId('detail')) {
    target.replaceChildren(); const actor = presentation.participants.get(id);
    if (!actor) { target.append(node('p', 'Участник отсутствует в снимке.')); return; }
    target.append(node('div', id, 'eyebrow'), node('h2', actor.label || id)); line(target, 'Роль на момент снимка', actor.role);
    line(target, 'Название сессии', actor.session_title); line(target, 'Примечание к истории', actor.history_note);
    if (typeof actor.session_url === 'string' && /^codex:\/\/threads\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(actor.session_url)) {
      const link = node('a', 'Открыть записанную сессию Codex', 'link'); link.href = actor.session_url; target.append(link);
      line(target, 'Точная ссылка сессии', actor.session_url);
    } else line(target, 'Точная ссылка на сессию', 'UNKNOWN / not declared');
    const related = works(snapshot).filter(w => actors(w).includes(id) || sourceActors(presentation, w.id).includes(id)); links(target, 'Связанные работы, включая исторические роли', related.map(w => w.id), 'work');
    [['actor_updates', 'Изменения ролей'], ['actor_events', 'История состояния участника'], ['activity_events', 'Наблюдения по точному шагу']].forEach(([key, title]) => {
      const rows = eventOrder(arr(presentation.matrix && presentation.matrix[key]).filter(e => e.actor_id === id));
      const box = node('details', null, 'source-history'); box.append(node('summary', `${title} · ${rows.length}`));
      rows.forEach(e => sourceEventDetail(box, e, title)); target.append(box);
    });
    const initial = arr(presentation.matrix && presentation.matrix.actors).find(a => a && typeof a === 'object' && a.id === id);
    if (initial) raw(target, 'Исходная запись участника', initial);
    target.append(node('p', 'Записанное состояние сессии или назначение не доказывают текущую активность работы. Модель, runtime, трудозатраты и ID сессии не выводятся автоматически.', 'note'));
  }
  function participantList(parent) {
    const rows = [...presentation.participants.values()].filter(a => searchable(a, state.query));
    byId('summary').textContent = `${rows.length} participants · original roster and dated role updates retained`;
    const grid = node('section', null, 'participant-grid');
    rows.forEach(a => {
      const card = node('article', null, 'card participant-card'), b = node('button', a.label || a.id, 'row-title'); b.dataset.actor = a.id;
      card.append(node('div', a.id, 'eyebrow'), b, node('p', a.role || 'Роль не указана'));
      if (a.session_title) card.append(node('p', a.session_title, 'note'));
      const count = works(snapshot).filter(w => actors(w).includes(a.id) || sourceActors(presentation, w.id).includes(a.id)).length;
      card.append(node('p', `${count} related work items, including historical roles`, 'note')); grid.append(card);
    }); parent.append(grid);
  }
  function sourceOverview(parent) {
    if (!presentation.matrix) {
      parent.append(node('p', `Owning matrix presentation: ${presentation.source.status}. Native Atlas records remain available.`, 'note')); return;
    }
    const matrix = presentation.matrix;
    if (matrix.snapshot_summary) parent.append(node('p', matrix.snapshot_summary, 'snapshot-summary'));
    parent.append(node('p', `Source matrix revision ${textValue(matrix.revision)} · ${matrix.steps.length} steps · ${matrix.events.length} work events · ${arr(matrix.actors).length} declared participants · updated ${textValue(matrix.updated_at)}`, 'note'));
    if (matrix.coverage && matrix.coverage.current_stage) links(parent, 'Текущий этап по источнику', [matrix.coverage.current_stage], 'work');
  }
  function counters(parent) {
    const all = works(snapshot), box = node('section', null, 'metrics'); box.setAttribute('aria-label', 'Все работы в этом снимке');
    [['Работ в снимке', all.length], ['В работе по Atlas', all.filter(w => w.state === 'DOING').length],
      ['Текущая активность', all.filter(w => displayActivity(w) === 'CURRENT').length], ['Принято по Atlas', all.filter(w => w.state === 'ACCEPTED').length],
      ['С блокером', all.filter(w => w.blocker || w.state === 'BLOCKED').length]].forEach(([title, value]) => {
      const metric = node('div', null, 'metric'); metric.append(node('strong', value), node('span', title)); box.append(metric);
    }); parent.append(box);
  }
  function coverage(parent) {
    const value = snapshot.atlas.coverage || {};
    const status = ['COMPLETE', 'PARTIAL', 'UNKNOWN'].includes(value.status) ? value.status : 'UNKNOWN';
    const box = node('details', null, 'coverage');
    box.append(node('summary', `Project coverage: ${status}${arr(value.domains).length ? ' · domains ' + value.domains.length : ''}`));
    box.append(node('p', 'Полнота оценивается по закреплённому инвентарю и явным исключениям.', 'note'));
    if (value.scope_note) line(box, 'Область инвентаризации', value.scope_note);
    if (value.observed_at) line(box, 'Инвентаризация зафиксирована', value.observed_at);
    if (!arr(value.domains).length) box.append(node('p', 'Область документации и полнота не установлены.', 'note'));
    arr(value.domains).forEach(domain => {
      line(box, `${textValue(domain.title || domain.id)} · ${textValue(domain.status)}`,
        `Documented: ${textValue(domain.documented_count)} / ${textValue(domain.inventory_count)}`);
      if (arr(domain.missing_ids).length) line(box, 'Не документировано', domain.missing_ids.join(', '));
      if (arr(domain.exclusions).length) line(box, 'Явные исключения инвентаризации', domain.exclusions);
    });
    issues(box, value.issues); parent.append(box);
  }
  const toolbar = byId('search').closest('.toolbar');
  const workFilters = node('div', null, 'work-filters');
  const stateSelect = node('select'); stateSelect.id = 'work-state';
  const actorSelect = node('select'); actorSelect.id = 'work-actor';
  if (isAtlas) {
    document.body && document.body.setAttribute('data-atlas', 'true');
    [['Все статусы', 'all'], ...Object.entries(STATES).map(([id, label]) => [`${id} · ${label}`, id])].forEach(([title, id]) => {
      const option = node('option', title); option.value = id; stateSelect.append(option);
    });
    if (presentation.matrix) [...new Set(presentation.matrix.events.map(e => e.status).filter(x => typeof x === 'string'))].sort().forEach(id => {
      const option = node('option', `Source · ${SOURCE_STATES[id] || id}`); option.value = 'source:' + id; stateSelect.append(option);
    });
    [['Все участники', ''], ...[...presentation.participants.values()].map(a => [a.label || a.id, a.id])].forEach(([title, id]) => {
      const option = node('option', title); option.value = id; actorSelect.append(option);
    });
    const stateLabel = node('label', 'Записанный статус'); stateLabel.append(stateSelect);
    const actorLabel = node('label', 'Участник работы'); actorLabel.append(actorSelect);
    workFilters.append(stateLabel, actorLabel); (toolbar || byId('modules')).append(workFilters);
    stateSelect.addEventListener('change', e => { state.workState = e.target.value; state.selection = null; render(); });
    actorSelect.addEventListener('change', e => { state.actor = e.target.value; state.selection = null; render(); });
    const eyebrow = byId('title').previousElementSibling;
    if (eyebrow) eyebrow.textContent = 'ATLAS · ROADMAP · CONTRACTS · PROJECT RECORDS';
    const overview = node('section', null, 'project-overview'); overview.id = 'project-overview'; sourceOverview(overview); byId('scope').parentElement.append(overview);
  }
  function sidebar() {
    const target = byId('modules'); target.replaceChildren();
    const heading = target.previousElementSibling;
    if (heading) heading.textContent = isAtlas && ['works', 'relations', 'history'].includes(state.tab) ? 'Проект' : 'Модули';
    if (isAtlas && ['works', 'relations', 'history'].includes(state.tab)) {
      line(target, 'Цель проекта', displayText(presentation,snapshot.atlas.project.id,'project.objective')); line(target, 'Владелец матрицы', snapshot.atlas.project.writer);
      target.append(node('p', 'Исторический статус и подтверждение активности — разные факты.', 'note'));
      return;
    }
    [['', 'Все модули'], ...arr(snapshot.input.modules).map(m => [m.id, m.title])].forEach(([id, title]) => {
      const b = node('button', title, 'module'); b.dataset.module = id; b.setAttribute('aria-pressed', String(state.module === id)); target.append(b);
    });
  }
  function render() {
    const ownerMode = !!(isAtlas && state.tab === 'works');
    const focus = document.activeElement, ownerFocus = focus && focus.closest && focus.closest('#owner-matrix') && focus.id ? {id: focus.id, start: focus.selectionStart, end: focus.selectionEnd} : null;
    ownerRemember();
    if (ownerPane.parentElement !== ownerPaneHome) ownerPaneHome.append(ownerPane);
    ownerPane.className = ''; delete ownerPane.dataset.ownerPanel;
    byId('search').value = state.query; byId('lifecycle').value = state.lifecycle;
    const project = isAtlas ? snapshot.atlas.project : snapshot.input.project;
    byId('title').textContent = isAtlas?projectDisplayTitle(snapshot):project.title;
    byId('release').textContent = isAtlas ? `Snapshot as of ${textValue(snapshot.atlas.as_of)} · data is not refreshed from sources automatically`
      : `${snapshot.template_version} · ${snapshot.input.release.id} · ${snapshot.input.release.created_at} · input SHA ${snapshot.input_sha256}`;
    byId('scope').textContent = (isAtlas ? displayText(presentation,project.id,'project.scope_note') : project.scope_note) || (isAtlas ? displayText(presentation,project.id,'project.objective') : 'Выбранные снимки документов. Эти записи не подтверждают выполнение runtime или приёмку. У каждого источника своё время проверки.');
    if (isAtlas && document.body) { document.body.setAttribute('data-view', state.tab); document.body.setAttribute('data-selected', String(!!state.selection)); }
    if (document.body) document.body.setAttribute('data-owner-matrix', String(ownerMode));
    byId('download').textContent = isAtlas ? 'Download document index' : 'Download DOCS_INDEX.json';
    byId('download').title = isAtlas ? 'Проекция документов: snapshot.input. Полный Atlas — в snapshot.json.' : 'Исходная структура индекса без дополнительной обёртки';
    byId('search').setAttribute('placeholder', state.tab === 'works' ? 'Title, ID, participant, path…' : 'Text, ID, parameter…');
    workFilters.hidden = state.tab !== 'works'; stateSelect.value = state.workState; actorSelect.value = state.actor;
    const versionLabel = byId('lifecycle').closest('label');
    if (versionLabel) versionLabel.hidden = isAtlas && !['documents', 'contracts', 'overview'].includes(state.tab);
    byId('tabs').replaceChildren();
    const tabs = isAtlas ? (state.tab === 'overview' ? [...ATLAS_TABS, ['overview', 'Модуль']] : ATLAS_TABS) : DOC_TABS;
    tabs.forEach(([id, title]) => {
      const b = node('button', ownerMode ? ({works: 'Матрица', contracts: 'Контракты', documents: 'Документы', actors: 'Участники', history: 'История', relations: 'Связи', coverage: 'Покрытие'}[id] || title) : title); b.dataset.tab = id; b.setAttribute('aria-pressed', String(state.tab === id));
      if (isAtlas) { const group = node('span', null, 'nav-section'); group.append(b); const link = node('a', '↗', 'section-permalink'); link.href = routeFor(id); link.setAttribute('aria-label', `Direct link to ${title}`); link.title = `Direct link to ${title}`; group.append(link); byId('tabs').append(group); }
      else byId('tabs').append(b);
    });
    sidebar();
    const rows = isAtlas && state.tab === 'history' ? presentationHistory(snapshot).filter(x => searchable(x, state.query)) : derive(snapshot, state); byId('list').replaceChildren();
    if (state.tab === 'works') {
      if (ownerMode) ownerMatrix(byId('list'));
      else { counters(byId('list')); coverage(byId('list')); roadmap(byId('list')); }
    } else byId('summary').textContent = `${rows.length} items · ${state.tab === 'matrix' ? 'selected snapshot: steps and historical events; version filters do not apply' : state.tab === 'history' ? isAtlas ? 'work and document events, newest first' : 'complete log, searchable by text' : isAtlas && state.tab === 'relations' ? 'explicit work, artifact and document relationships' : state.lifecycle === 'current' ? 'current versions' : state.lifecycle === 'archived' ? 'archived versions' : 'all versions'}`;
    if (isAtlas && state.tab === 'actors') participantList(byId('list'));
    if (isAtlas && state.tab === 'coverage') {
      byId('summary').textContent = 'Declared project inventory, source limits and preserved gaps';
      coverage(byId('list'));
      if (presentation.matrix) {
        raw(byId('list'), 'Source coverage and outstanding gaps', presentation.matrix.coverage);
        raw(byId('list'), 'Source policy', presentation.matrix.policy);
      }
      issues(byId('list'), [...presentation.issues, ...arr(snapshot.atlas.issues)]);
      const info = node('details', null, 'raw-data'); info.append(node('summary', 'Pinned sources / presentation binding'));
      raw(info, 'Pinned source files', snapshot.atlas.source_pins); raw(info, 'Presentation binding', snapshot.atlas.presentation || {status: presentation.source.status}); byId('list').append(info);
    }
    if (isAtlas && state.tab === 'history') {
      const revisions = arr(snapshot.atlas.matrix_history).length ? snapshot.atlas.matrix_history : snapshot.atlas.revisions;
      const box = node('details', null, 'raw-data');
      box.append(node('summary', 'Matrix version history'));
      box.append(node('p', 'Здесь показаны события текущего снимка. Полная неизменяемая история выпусков хранится отдельно; ссылки ниже относятся только к включённым записям.', 'note'));
      if (revisions === undefined || revisions === null || (Array.isArray(revisions) && !revisions.length)) box.append(node('p', 'В снимке нет ссылок на предыдущие выпуски. Полнота истории: UNKNOWN.', 'note'));
      else box.append(node('pre', JSON.stringify(revisions, null, 2)));
      if (Number.isInteger(snapshot.atlas.matrix_history_total)) line(box, 'Total retained full matrices across releases', snapshot.atlas.matrix_history_total);
      const archive = snapshot.atlas.projection_archive;
      if (archive && typeof archive.previous_release === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(archive.previous_release)) {
        const pathname = typeof window !== 'undefined' && window.location && window.location.pathname;
        const release = snapshot.input && snapshot.input.release && snapshot.input.release.id;
        const inRelease = typeof pathname === 'string' && typeof release === 'string' && pathname.endsWith(`/releases/${encodeURIComponent(release)}/index.html`);
        const atCurrent = typeof pathname === 'string' && pathname.endsWith('/index.html') && !pathname.includes('/releases/');
        const link = node(inRelease || atCurrent ? 'a' : 'span', `Previous immutable release · ${archive.previous_release}`, 'link');
        if (inRelease || atCurrent) link.href = `${inRelease ? '../' : 'releases/'}${encodeURIComponent(archive.previous_release)}/index.html#history`;
        box.append(link);
        if (!inRelease && !atCurrent) box.append(node('p', 'Для экспортированного снимка местоположение архива не проверено. Откройте историю через Atlas проекта.', 'note'));
        line(box, 'Previous manifest SHA256', archive.previous_manifest_sha256);
      }
      if (presentation.matrix) box.append(node('p', `Included source records: ${presentation.matrix.events.length} work events; ${arr(presentation.matrix.actor_events).length} participant events; ${arr(presentation.matrix.actor_updates).length} role updates; ${arr(presentation.matrix.activity_events).length} activity observations. Atlas import events remain a separate history layer.`, 'note'));
      byId('list').append(box);
    }
    if (!rows.length && !['works', 'actors', 'coverage'].includes(state.tab)) byId('list').append(node('p', 'Ничего не найдено. «Сбросить фильтры» вернёт текущие записи.', 'empty'));
    (isAtlas && ['works', 'actors', 'coverage'].includes(state.tab) ? [] : rows).forEach(item => {
      const card = node('article', null, 'card');
      if (state.tab === 'matrix') {
        card.append(node('div', `${item.matrix_kind === 'step' ? 'Шаг' : 'Historical event'} · ${item.id}${item.at ? ' · ' + item.at : ''}`, 'eyebrow'));
        const b = node('button', workDisplayTitle(presentation,item), 'row-title'); b.dataset.matrix = `${item.matrix_kind}:${item.id}`; card.append(b);
      } else if (state.tab === 'history') {
        if (item.origin) card.append(node('div', item.origin, 'history-origin'));
        card.append(node('div', `${item.at} · ${item.id} · ${item.kind}${item.actor ? ' · ' + item.actor : ''}`, 'eyebrow'), node('p', item.summary));
        if (item.atlas_work_id) links(card, 'Работа', [item.atlas_work_id], 'work'); else links(card, 'Объекты', item.entity_ids);
        if (arr(item.evidence_ids).length) line(card, 'Evidence', item.evidence_ids.join(', '));
        if (item.raw && Number.isInteger(item.source_index)) sourceEventDetail(card, item.raw, item.origin);
      } else if (state.tab === 'relations') {
        card.append(node('div', item.type, 'eyebrow'));
        const row = node('div', null, 'edge');
        [item.from, item.to].forEach((id, index) => {
          if (index) row.append(node('span', ' → ', 'direction'));
          const isWork = item.atlas_relation === 'work' || (!!item.atlas_relation && item.atlas_relation !== 'document' && index === 0);
          if (item.atlas_relation === 'patch' && index === 1) row.append(node('span', id)); else row.append(linkButton(id, isWork ? 'work' : 'entity'));
        }); card.append(row);
        if (item.artifact) { line(card, 'Путь артефакта', item.artifact.path); patchDetail(card, item.artifact); }
        if (item.evidence_docs) links(card, 'Evidence', item.evidence_docs);
      } else {
        const b = node('button', workDisplayTitle(presentation,item), 'row-title'); b.dataset.entity = item.id;
        card.append(node('div', `${item.id}${item.version ? ' · ' + item.version : ''}`, 'eyebrow'), b, badges(item));
        card.append(node('p', item.purpose || item.input || item.source_ref, 'note'));
        if (isAtlas && item.contract_key) {
          line(card, 'Выход', item.output); line(card, 'Владелец состояния', item.state_owner);
          card.append(node('p', `${arr(item.parameters).length} parameters · ${arr(item.errors).length} declared errors · ${arr(item.docs).length} source documents`, 'note'));
        }
        if (isAtlas) { const link = node('a', 'Прямая ссылка', 'direct-link'); link.href = entityRoute(item.id); card.append(link); }
      }
      byId('list').append(card);
    });
    if (ownerMode) {
      if (ownerFocus) { const e = byId(ownerFocus.id); if (e && typeof e.focus === 'function') { e.focus({preventScroll: true}); if (typeof e.setSelectionRange === 'function' && Number.isInteger(ownerFocus.start)) e.setSelectionRange(ownerFocus.start, ownerFocus.end); } }
      if (ownerView.focusRow) { const e = ownerAll().find(e => e.dataset.stepId === ownerView.focusRow); if (e && typeof e.focus === 'function') e.focus({preventScroll: true}); ownerView.focusRow = null; }
      return;
    }
    if (state.selectionKind === 'actor') participantDetail(state.selection);
    else if (state.selectionKind === 'work' && findWork(snapshot, state.selection)) workDetail(findWork(snapshot, state.selection));
    else detail(state.selection ? find(snapshot, state.selection) : null);
  }
  function downloadText(value, filename, mime = 'application/json;charset=utf-8') {
    const url = URL.createObjectURL(new Blob([value], {type: mime}));
    const a = node('a'); a.href = url; a.download = filename; a.click();
    if (typeof setTimeout === 'function') setTimeout(() => URL.revokeObjectURL(url), 1000); else URL.revokeObjectURL(url);
  }
  function download(value, filename) { downloadText(JSON.stringify(value, null, 2), filename); }
  function copyFallback(text, workId, unfinishedOnly = false, exactSelected = false) {
    // The complete Markdown stays in a selectable textarea; no silent truncation on clipboard refusal.
    const old = document.getElementById('atlas-copy-fallback'); if (old) old.remove();
    const box = node('dialog'); box.id = 'atlas-copy-fallback'; box.setAttribute('aria-label', 'Контекст работы для ручного копирования: ' + workId);
    const title = node('h3', 'Буфер обмена недоступен — скопируйте полный контекст вручную');
    const body = node('textarea'); body.readOnly = true; body.value = text; body.rows = 18; body.setAttribute('aria-label', 'Полный контекст работы ' + workId);
    body.style.width = 'min(90vw, 900px)'; body.style.maxWidth = '90vw'; body.style.height = '55vh';
    const save = node('button','Скачать полный пакет .md + SHA256');
    if(!exactSelected){save.dataset[unfinishedOnly ? 'ownerBundleUnfinished' : 'ownerBundle']=workId;}else save.addEventListener('click',async()=>{try{const bytes=new TextEncoder().encode(text),digest=await crypto.subtle.digest('SHA-256',bytes),sha=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');downloadText('# Atlas selected handoff companion\n\n'+JSON.stringify({schema:'atlas.selected-companion/v1',body_bytes:bytes.length,body_sha256:sha},null,2)+'\n\n'+text,'atlas-selected.md','text/markdown;charset=utf-8')}catch(error){save.textContent='SHA256 недоступен — скопируйте текст вручную'}});
    save.setAttribute('aria-label','Скачать полный контекст для ручной передачи: ' + workId);
    const close = node('button', 'Закрыть'); close.addEventListener('click', () => { if (typeof box.close === 'function') box.close(); box.remove(); });
    box.append(title, body, save, close); document.body.append(box);
    if (typeof box.showModal === 'function') box.showModal(); else box.setAttribute('open', '');
    if (typeof body.focus === 'function') body.focus(); if (typeof body.select === 'function') body.select();
  }
  async function downloadWorkCompanion(workId, unfinishedOnly = false) {
    try {
      const candidate=await buildWorkHandoffCompanion(snapshot,workId,{unfinishedOnly});
      downloadText(candidate.text,candidate.filename,'text/markdown;charset=utf-8');
    } catch (error) {
      copyFallback('Не удалось подготовить подтверждённый SHA256 companion: ' + String(error),workId,unfinishedOnly);
    }
  }
  async function copyWork(workId, button, unfinishedOnly = false) {
    let packet;
    try { packet = unfinishedOnly ? buildUnfinishedHandoff(snapshot,workId) : buildWorkHandoff(snapshot, workId); }
    catch (error) { copyFallback('Контекст не собран: ' + String(error), workId,unfinishedOnly); return; }
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') throw Error('CLIPBOARD_UNAVAILABLE');
      await navigator.clipboard.writeText(packet);
      button.textContent = 'Скопировано';
      button.setAttribute('aria-label', (unfinishedOnly ? 'Невыполненные работы скопированы: ' : 'Полный контекст скопирован: ') + workId);
      button.title = packet.length > 500000
        ? 'Большой пакет полностью записан в буфер. Если чат ограничивает объём вставки, используйте рядом ↓ .md: полный контекст с проверяемым SHA256.'
        : 'Полный контекст записан в буфер';
    } catch (_) { copyFallback(packet, workId,unfinishedOnly); }
  }
  if(typeof window!=='undefined'&&window.addEventListener)window.addEventListener('resize',()=>{const root=byId('owner-matrix');if(root)atlasFitOwnerColumns(root)});
  document.addEventListener('click', e => {
    const actorLink = e.target.closest('a');
    if (isAtlas && actorLink && actorLink.dataset.ownerActor) {
      if (e.preventDefault) e.preventDefault(); ownerView.roster = true;
      const roster = byId('roster'), card = byId('actor-' + encodeURIComponent(actorLink.dataset.ownerActor));
      if (roster) { roster.open = true; for(let parent=roster.parentElement;parent;parent=parent.parentElement)if(String(parent.tagName).toLowerCase()==='details')parent.open=true; } if (card && typeof card.scrollIntoView === 'function') card.scrollIntoView({block: 'nearest'}); return;
    }
    const b = e.target.closest('button'); if (!b || b.disabled) return;
    if(b.dataset.atlasStatus||b.dataset.atlasUnfinishedAll){
      if(e.preventDefault)e.preventDefault();
      const scope=b.dataset.atlasScope==='ALL'?null:b.dataset.atlasScope||null;
      let ids=b.dataset.atlasUnfinishedAll?atlasStatusIds(snapshot).filter(id=>atlasStatusKind(presentation,id)!=='done'):atlasStatusIds(snapshot,scope,b.dataset.atlasStatus,!!scope);
      if(!scope&&!b.dataset.atlasUnfinishedAll&&countOwnerStatuses(snapshot,presentation).basis==='EXACT_SOURCE_STEPS')ids=ids.filter(id=>presentation.sourceSteps.has(id));
      let packet;try{packet=buildSelectedHandoff(snapshot,ids,scope)}catch(error){copyFallback('ТЗ не собрано: '+String(error),scope||'ALL');return}
      Promise.resolve().then(()=>{if(!navigator?.clipboard?.writeText)throw Error('CLIPBOARD_UNAVAILABLE');return navigator.clipboard.writeText(packet)}).then(()=>{b.title='Полное ТЗ скопировано';b.setAttribute('aria-label','Полное ТЗ скопировано')}).catch(()=>{
        copyFallback(packet,scope||'ALL',false,true);
      });return;
    }
    if (b.dataset.ownerCopyUnfinished) {
      if (e.preventDefault) e.preventDefault();
      if (e.stopPropagation) e.stopPropagation();
      void copyWork(b.dataset.ownerCopyUnfinished,b,true); return;
    }
    if (b.dataset.ownerBundleUnfinished) {
      if (e.preventDefault) e.preventDefault();
      if (e.stopPropagation) e.stopPropagation();
      void downloadWorkCompanion(b.dataset.ownerBundleUnfinished,true); return;
    }
    if (b.dataset.ownerCopy) { if (e.preventDefault) e.preventDefault(); if (e.stopPropagation) e.stopPropagation(); void copyWork(b.dataset.ownerCopy, b); return; }
    if (b.dataset.ownerBundle) { if (e.preventDefault) e.preventDefault(); if (e.stopPropagation) e.stopPropagation(); void downloadWorkCompanion(b.dataset.ownerBundle); return; }
    if (b.dataset.ownerDetail) {
      const id = b.dataset.ownerDetail; ownerView.details.has(id) ? ownerView.details.delete(id) : ownerView.details.add(id);
      state.selection = ownerView.details.has(id) ? id : null; state.selectionKind = state.selection ? 'work' : null; ownerView.focusRow = id; render();
    }
    else if (b.dataset.ownerActive) { state.activeOnly = !state.activeOnly; state.query = ''; state.actor = ''; state.workState = 'all'; state.filterCollapsed.clear(); render(); }
    else if (b.dataset.ownerRecover) { reset(state); state.workState = b.dataset.ownerRecover === 'journal' ? 'journal:doing' : 'all'; state.expanded = new Set(presentation.byId.keys()); state.filterCollapsed.clear(); render(); }
    else if (b.dataset.ownerRefresh) ownerRefresh(true);
    else if (b.dataset.tab) { if (isAtlas) goRoute(routeFor(b.dataset.tab)); else { state.tab = b.dataset.tab; state.selection = null; state.selectionKind = null; render(); } }
    else if (b.dataset.work) { if (isAtlas) goRoute(routeFor('work', b.dataset.work)); else if (openWork(snapshot, state, b.dataset.work)) render(); }
    else if (b.dataset.entity) { if (isAtlas) goRoute(entityRoute(b.dataset.entity)); else if (openEntity(snapshot, state, b.dataset.entity)) render(); }
    else if (b.dataset.actor) goRoute(routeFor('actor', b.dataset.actor));
    else if (b.dataset.toggle) {
      const filtered = state.query || state.actor || state.activeOnly || state.workState !== 'all', set = filtered ? state.filterCollapsed : state.expanded;
      ownerView.focusRow = b.dataset.toggle;
      set.has(b.dataset.toggle) ? set.delete(b.dataset.toggle) : set.add(b.dataset.toggle); render();
    }
    else if (b.dataset.expandAll) { state.expanded = new Set(presentation.byId.keys()); state.filterCollapsed.clear(); render(); }
    else if (b.dataset.collapseAll) { state.expanded.clear(); state.filterCollapsed = new Set(presentation.byId.keys()); ownerView.details.clear(); state.selection = null; state.selectionKind = null; render(); }
    else if (b.dataset.activeOnly) { state.activeOnly = !state.activeOnly; state.filterCollapsed.clear(); render(); }
    else if (b.dataset.module !== undefined) { state.module = b.dataset.module; render(); }
    else if (b.dataset.snapshotDownload) download(snapshot, 'snapshot.json');
    else if (b.dataset.matrixDownload) { if (presentation.matrix && presentation.source.document) downloadText(presentation.source.document.content, 'owning-matrix.json'); }
    else if (b.dataset.matrix) {
      const [kind, ...rest] = b.dataset.matrix.split(':'), id = rest.join(':');
      const m = snapshot.matrix_snapshot; if (!m) return;
      const item = (kind === 'step' ? arr(m.steps) : arr(m.events)).find(x => x.id === id); if (!item) return;
      byId('detail').replaceChildren(node('h2', workDisplayTitle(presentation,item)), node('pre', JSON.stringify(item, null, 2)));
      line(byId('detail'), 'Набор данных', m.dataset_id); links(byId('detail'), 'Источник с SHA и проверкой', snapshot.input.matrix ? [snapshot.input.matrix.doc] : []);
      const linked = arr(snapshot.input.bindings).filter(x => arr(kind === 'step' ? x.step_ids : x.event_ids).includes(id)).map(x => x.entity_id);
      links(byId('detail'), 'Linked documents/contracts', linked);
      if (kind === 'event') arr(item.step_ids).forEach(step => { const link = node('button', `Step · ${step}`, 'link'); link.dataset.matrix = `step:${step}`; byId('detail').append(link); });
    }
  });
  byId('search').addEventListener('input', e => { state.query = e.target.value; if (state.filterCollapsed) state.filterCollapsed.clear(); render(); });
  byId('lifecycle').addEventListener('change', e => { state.lifecycle = e.target.value; render(); });
  byId('reset').addEventListener('click', () => { reset(state); if (state.filterCollapsed) state.filterCollapsed.clear(); render(); });
  byId('download').addEventListener('click', () => download(exportIndex(snapshot), 'DOCS_INDEX.json'));
  if (isAtlas && typeof window !== 'undefined' && window.location) {
    applyRoute(window.location.hash);
    if (ownerView.restore && (!window.location.hash || window.location.hash === '#roadmap')) {
      const saved = ownerView.restore; state.query = saved.query; state.actor = saved.actor; state.workState = saved.workState; state.activeOnly = saved.activeOnly;
      state.filterCollapsed = new Set(saved.filterCollapsed);
    }
    if (typeof window.addEventListener === 'function') window.addEventListener('hashchange', () => { applyRoute(window.location.hash); render(); });
    if (typeof window.addEventListener === 'function') window.addEventListener('pagehide', ownerSave);
  }
  if (isAtlas) ['input', 'pointerdown', 'scroll'].forEach(kind => document.addEventListener(kind, () => { ownerView.lastInteraction = Date.now(); }, true));
  render();
  if (ownerView.restore && typeof window !== 'undefined' && typeof window.scrollTo === 'function') window.scrollTo({top: Math.max(0, Number(ownerView.restore.scrollY) || 0), left: Math.max(0, Number(ownerView.restore.scrollX) || 0), behavior: 'instant'});
  if (isAtlas && typeof setInterval === 'function') setInterval(() => ownerRefresh(false), 30000);
  if (isAtlas && typeof setInterval === 'function') setInterval(() => {
    const before = JSON.stringify([[...agedActivity], [...agedSourceActivity]]); works(snapshot).forEach(w => { displayActivity(w); displaySourceActivity(w.id); });
    if (JSON.stringify([[...agedActivity], [...agedSourceActivity]]) !== before) render();
    ownerUpdateClocks();
  }, 1000);
}());
