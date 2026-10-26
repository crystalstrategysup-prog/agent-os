"""One-shot stdio bridge to the existing supported app read_thread tool.

No daemon, RPC override, dynamic method dispatch or recorded-evidence input.
The owning caller must execute the exact challenged supported tool and preserve
its real result; stdin alone does not authenticate that caller's provenance.
"""
from __future__ import annotations
import json
import os
import select
import sys
import time
import uuid
from . import interrupted_continuation as c

TOOL='mcp__codex_app__read_thread'
MAX_RESPONSE=c.METADATA_WIRE_LIMIT


def check_params(params,native_thread_id=None):
    if not isinstance(params,dict)or set(params)-{'threadId','turnLimit','includeOutputs','maxOutputCharsPerItem','cursor'}:c.fail('bridge_method_or_params')
    if not isinstance(params.get('threadId'),str)or not params['threadId']or len(params['threadId'])>4096:c.fail('bridge_method_or_params')
    if native_thread_id is not None and params['threadId']!=native_thread_id:c.fail('bridge_method_or_params')
    if type(params.get('turnLimit'))is not int or params['turnLimit']!=c.OBSERVER_TURN_LIMIT or params.get('includeOutputs')is not False or type(params.get('maxOutputCharsPerItem'))is not int or params['maxOutputCharsPerItem']!=80:c.fail('bridge_method_or_params')
    if 'cursor'in params and (not isinstance(params['cursor'],str)or not params['cursor']or len(params['cursor'])>2048):c.fail('bridge_method_or_params')


class MetadataResponseAccounting:
    """In-memory per-operation original-byte budget at the trusted tool boundary."""
    def __init__(self,request_sha256,native_thread_id):
        self.request_sha256=request_sha256;self.native_thread_id=native_thread_id
        self.total_original_bytes=0;self.calls=0;self.nonces=set()
    def charge(self,challenge,size):
        if challenge['request_sha256']!=self.request_sha256 or challenge['params']['threadId']!=self.native_thread_id:c.fail('bridge_response_binding')
        nonce=challenge['nonce']
        if not isinstance(nonce,str)or not c.re.fullmatch('[0-9a-f]{32}',nonce)or nonce in self.nonces:c.fail('bridge_response_binding')
        if self.calls>=c.OBSERVER_MAX_PAGES:c.fail('bridge_call_limit')
        if size>c.OBSERVER_MAX_RESPONSE or self.total_original_bytes+size>c.OBSERVER_MAX_TOTAL_RESPONSE:c.fail('provider_response_limit')
        self.calls+=1;self.nonces.add(nonce);self.total_original_bytes+=size


def prepare_metadata_response(challenge,actual_supported_result,*,accounting=None):
    """Trusted integration boundary: measure full actual result BEFORE stripping.

    Use only on an actual supported-tool return held in memory. Never print or
    store the original envelope. This helper cannot authenticate its caller.
    """
    c.rr.keys(challenge,'schema tool params nonce request_sha256')
    if challenge['schema']!='agentos.app-tool-metadata-challenge/v2'or challenge['tool']!=TOOL:c.fail('bridge_response_binding')
    check_params(challenge['params'])
    size=len(c.provider_encoded(actual_supported_result))
    if not isinstance(accounting,MetadataResponseAccounting):c.fail('bridge_accounting_required')
    # Per-response AND aggregate original-byte limits precede all stripping.
    accounting.charge(challenge,size)
    result=c.metadata_page(actual_supported_result)
    response={**challenge,'schema':'agentos.app-tool-metadata-result/v2','original_response_bytes':size,'result':result}
    if len(c.provider_encoded(response))>MAX_RESPONSE:c.fail('bridge_response_limit')
    return response

class StdioToolBridge:
    def __init__(self,request_sha256,*,native_thread_id,input_fd=None,output=None,timeout=45,total_timeout=120):
        if not 0<timeout<=45 or not timeout<=total_timeout<=120:c.fail('bridge_timeout')
        self.request_sha256=request_sha256;self.native_thread_id=native_thread_id;self.input_fd=sys.stdin.fileno()if input_fd is None else input_fd
        self.output=output or sys.stdout;self.timeout=timeout;self.deadline=time.monotonic()+total_timeout
        self.calls=0;self.total_response_bytes=0;self.total_wire_bytes=0

    def __call__(self,**params):
        check_params(params,self.native_thread_id)
        if self.calls>=c.OBSERVER_MAX_PAGES:c.fail('bridge_call_limit')
        if self.total_response_bytes>=c.OBSERVER_MAX_TOTAL_RESPONSE:c.fail('bridge_response_limit')
        if time.monotonic()>=self.deadline:c.fail('bridge_timeout')
        self.calls+=1
        nonce=uuid.uuid4().hex;deadline=min(self.deadline,time.monotonic()+self.timeout)
        request={'schema':'agentos.app-tool-metadata-challenge/v2','tool':TOOL,'params':params,'nonce':nonce,'request_sha256':self.request_sha256}
        self.output.write(json.dumps(request,separators=(',',':'))+'\n');self.output.flush();raw=bytearray()
        while b'\n'not in raw:
            left=deadline-time.monotonic()
            if left<=0 or not select.select([self.input_fd],[],[],max(0,left))[0]:c.fail('bridge_timeout')
            piece=os.read(self.input_fd,min(65536,MAX_RESPONSE+1-len(raw)))
            if not piece:c.fail('bridge_closed')
            raw.extend(piece)
            self.total_wire_bytes+=len(piece)
            if len(raw)>MAX_RESPONSE:c.fail('bridge_response_limit')
            if time.monotonic()>=deadline:c.fail('bridge_timeout')
        line,rest=bytes(raw).split(b'\n',1)
        if rest:c.fail('bridge_unsolicited_data')
        response=c.rr.parse(line);c.rr.keys(response,'schema tool params nonce request_sha256 original_response_bytes result')
        if response.get('schema')!='agentos.app-tool-metadata-result/v2' or any(c.encoded(response.get(k))!=c.encoded(request[k])for k in ['tool','params','nonce','request_sha256']):c.fail('bridge_response_binding')
        if not isinstance(response['result'],dict):c.fail('bridge_response')
        envelope=c.ProviderMetadataEnvelope(response['result'],response['original_response_bytes'])
        self.total_response_bytes+=envelope.original_response_bytes
        if self.total_response_bytes>c.OBSERVER_MAX_TOTAL_RESPONSE:c.fail('bridge_response_limit')
        if time.monotonic()>=deadline:c.fail('bridge_timeout')
        return envelope


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['advance','reconcile','observe-only'])
    parser.add_argument('--root',required=True,type=c.Path)
    parser.add_argument('--home',required=True,type=c.Path)
    parser.add_argument('--request',required=True,type=c.Path)
    parser.add_argument('--permit',type=c.Path)
    args=parser.parse_args(argv);r=c.rr.document(args.request)
    c.validate_request(args.root.resolve(),args.home.resolve(),r)
    bridge=StdioToolBridge(c.sha(c.encoded(r)),native_thread_id=r['native_thread_id']);observer=c.SupportedReadThreadObserver(bridge)
    if args.action=='observe-only':
        result={'status':'PROVIDER_METADATA_ONLY_NOT_TASK_ADMISSION','observation':observer.read_turn_metadata(r,c.sha(c.encoded(r))),'effects':False}
    else:
        if args.permit is None:c.fail('authority_required')
        authority=c.rr.document(args.permit);fn=c.advance if args.action=='advance'else c.reconcile
        result=fn(args.root,args.home,r,authority,observer=observer)
    print(json.dumps({'schema':'agentos.app-tool-final/v1','result':result},separators=(',',':')),flush=True)
    return 0

if __name__=='__main__':
    previous_tty=None
    try:
        if sys.stdin.isatty():
            import termios
            previous_tty=termios.tcgetattr(sys.stdin.fileno());settings=list(previous_tty);settings[6]=list(previous_tty[6])
            settings[3]&=~(termios.ECHO|termios.ICANON);settings[6][termios.VMIN]=1;settings[6][termios.VTIME]=0
            termios.tcsetattr(sys.stdin.fileno(),termios.TCSANOW,settings)
        sys.exit(main())
    except c.GateError as exc:
        print(json.dumps({'status':'BLOCKED','error':str(exc)}),flush=True);sys.exit(2)
    finally:
        if previous_tty is not None:termios.tcsetattr(sys.stdin.fileno(),termios.TCSANOW,previous_tty)

