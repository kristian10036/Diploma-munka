(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.SpectrumFrameAdapter = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const MAX_POINTS = 65536;
  const REQUIRED_V1 = ['schema_version','sensor_id','source_type','source_device','device_model','measurement_mode','session_id','timestamp','sequence','start_frequency_hz','stop_frequency_hz','step_frequency_hz','center_frequency_hz','sample_rate_hz','rbw_hz','num_points','point_count','power_unit','powers_dbm','flags','metadata'];
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const fail = message => { throw new TypeError(`Hibás SpectrumFrame: ${message}`); };

  function axis(startHz, stepHz, count) {
    const values = new Float64Array(count);
    for (let index=0; index<count; index+=1) values[index]=startHz+stepHz*index;
    return values;
  }
  function base(fields) {
    return Object.assign({schemaVersion:null,sensorId:null,sourceType:'legacy',sourceDevice:'legacy-websocket',sessionId:null,timestamp:null,sequence:null,centerFrequencyHz:null,sampleRateHz:null,rbwHz:null,flags:{},metadata:{is_simulated:false}}, fields);
  }
  function parseV1(frame) {
    for (const field of REQUIRED_V1) if (!Object.prototype.hasOwnProperty.call(frame,field)) fail(`hiányzó mező: ${field}`);
    if (frame.schema_version!==1 || frame.power_unit!=='dBm') fail('nem támogatott séma vagy mértékegység');
    if (!['mock','replay','aaronia','usrp','hackrf'].includes(frame.source_type)) fail('érvénytelen source_type');
    for (const field of ['sensor_id','source_device','device_model','measurement_mode','session_id','timestamp']) if (typeof frame[field]!=='string' || !frame[field]) fail(`érvénytelen ${field}`);
    if (!/(Z|[+-]\d{2}:\d{2})$/.test(frame.timestamp) || !Number.isFinite(Date.parse(frame.timestamp))) fail('érvénytelen timestamp');
    for (const field of ['sequence','start_frequency_hz','stop_frequency_hz','step_frequency_hz','center_frequency_hz','sample_rate_hz','num_points']) if (!Number.isSafeInteger(frame[field])) fail(`érvénytelen egész mező: ${field}`);
    if (frame.sequence<0 || frame.num_points<1 || frame.num_points>MAX_POINTS || frame.point_count!==frame.num_points) fail('érvénytelen sequence vagy pontszám');
    if (frame.step_frequency_hz<1 || frame.sample_rate_hz<1) fail('érvénytelen step vagy sample rate');
    const expectedStop=frame.start_frequency_hz+frame.step_frequency_hz*(frame.num_points-1);
    if (!Number.isSafeInteger(expectedStop) || expectedStop!==frame.stop_frequency_hz) fail('inkonzisztens frekvenciatengely');
    if (frame.start_frequency_hz>=frame.stop_frequency_hz) fail('üres frekvenciatartomány');
    if (frame.center_frequency_hz<frame.start_frequency_hz || frame.center_frequency_hz>frame.stop_frequency_hz) fail('center a tartományon kívül');
    if (!finite(frame.rbw_hz) || frame.rbw_hz<=0) fail('érvénytelen RBW');
    if (!Array.isArray(frame.powers_dbm) || frame.powers_dbm.length!==frame.num_points) fail('a num_points és powers_dbm eltér');
    if (!frame.powers_dbm.every(finite)) fail('NaN vagy Infinity teljesítményérték');
    if (!frame.flags || typeof frame.flags!=='object' || !['overflow','dropped','inaccurate'].every(key=>typeof frame.flags[key]==='boolean') || !frame.metadata || typeof frame.metadata!=='object') fail('érvénytelen flags vagy metadata');
    if (['mock','replay'].includes(frame.source_type) && frame.metadata.is_simulated!==true) fail('a mock/replay adat nincs szimuláltként jelölve');
    return base({format:'spectrum-frame-v1',schemaVersion:1,sensorId:frame.sensor_id,sourceType:frame.source_type,sourceDevice:frame.source_device,deviceModel:frame.device_model,measurementMode:frame.measurement_mode,sessionId:frame.session_id,timestamp:frame.timestamp,sequence:frame.sequence,startFrequencyHz:frame.start_frequency_hz,stopFrequencyHz:frame.stop_frequency_hz,stepFrequencyHz:frame.step_frequency_hz,centerFrequencyHz:frame.center_frequency_hz,sampleRateHz:frame.sample_rate_hz,rbwHz:frame.rbw_hz,numPoints:frame.num_points,frequenciesHz:axis(frame.start_frequency_hz,frame.step_frequency_hz,frame.num_points),powersDbm:Float32Array.from(frame.powers_dbm),flags:Object.assign({},frame.flags),metadata:Object.assign({},frame.metadata)});
  }
  function parsePoints(points) {
    if (points.length<1 || points.length>MAX_POINTS) fail('érvénytelen legacy pontszám');
    const normalized=points.map(point=>{if(!point || typeof point!=='object') fail('érvénytelen legacy pont'); const mhz=Number(point.x??point.freq),dbm=Number(point.y??point.dbm); if(!Number.isFinite(mhz)||!Number.isFinite(dbm)) fail('érvénytelen legacy pont'); return {hz:mhz*1e6,dbm};}).sort((a,b)=>a.hz-b.hz);
    for(let i=1;i<normalized.length;i+=1) if(normalized[i].hz<=normalized[i-1].hz) fail('a legacy frekvenciák nem egyediek');
    const frequencies=Float64Array.from(normalized,p=>p.hz);
    return base({format:'legacy-points',startFrequencyHz:frequencies[0],stopFrequencyHz:frequencies[frequencies.length-1],stepFrequencyHz:frequencies.length>1?frequencies[1]-frequencies[0]:null,centerFrequencyHz:(frequencies[0]+frequencies[frequencies.length-1])/2,numPoints:frequencies.length,frequenciesHz:frequencies,powersDbm:Float32Array.from(normalized,p=>p.dbm)});
  }
  function parseNumbers(values,options) {
    if(values.length<2 || values.length>MAX_POINTS || !values.every(finite)) fail('érvénytelen legacy számtömb');
    const start=options.legacyStartFrequencyHz,stop=options.legacyStopFrequencyHz;
    if(!finite(start)||!finite(stop)||start>=stop) fail('a számtömbhöz érvényes legacy tartomány kell');
    const step=(stop-start)/(values.length-1);
    return base({format:'legacy-numbers',startFrequencyHz:start,stopFrequencyHz:stop,stepFrequencyHz:step,centerFrequencyHz:(start+stop)/2,numPoints:values.length,frequenciesHz:axis(start,step,values.length),powersDbm:Float32Array.from(values)});
  }
  function parseSpectrumFrame(payload,options={}) {
    if(payload && typeof payload==='object' && !Array.isArray(payload)) return parseV1(payload);
    if(!Array.isArray(payload)||payload.length===0) fail('üres vagy ismeretlen payload');
    return typeof payload[0]==='number'?parseNumbers(payload,options):parsePoints(payload);
  }
  function createSequenceTracker(){const last=new Map();return{observe(frame){if(frame.sequence===null)return{gap:0,previous:null};const key=`${frame.sensorId}\u001f${frame.sessionId}\u001f${frame.sourceType}`,previous=last.has(key)?last.get(key):null,gap=previous===null?0:Math.max(0,frame.sequence-previous-1);last.set(key,frame.sequence);return{gap,previous};},reset(){last.clear();}};}
  function isStale(frame,nowMs,thresholdMs){if(!frame||!frame.timestamp)return false;const measured=Date.parse(frame.timestamp);return Number.isFinite(measured)&&nowMs-measured>thresholdMs;}
  return {MAX_POINTS,parseSpectrumFrame,createSequenceTracker,isStale};
});
