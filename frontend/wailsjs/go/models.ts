export namespace bindings {
	
	export class CreateTaskReq {
	    url: string;
	    saveDir: string;
	    concurrency: number;
	    partSize: number;
	    maxRetry: number;
	    timeout: number;
	
	    static createFrom(source: any = {}) {
	        return new CreateTaskReq(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.url = source["url"];
	        this.saveDir = source["saveDir"];
	        this.concurrency = source["concurrency"];
	        this.partSize = source["partSize"];
	        this.maxRetry = source["maxRetry"];
	        this.timeout = source["timeout"];
	    }
	}
	export class PreflightResult {
	    available: number;
	    silent: number;
	    total: number;
	    silentDomains: string[];
	
	    static createFrom(source: any = {}) {
	        return new PreflightResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.available = source["available"];
	        this.silent = source["silent"];
	        this.total = source["total"];
	        this.silentDomains = source["silentDomains"];
	    }
	}
	export class ProxyItem {
	    domain: string;
	    enabled: boolean;
	    status: string;
	    latency: string;
	    speed: string;
	    type: string;
	
	    static createFrom(source: any = {}) {
	        return new ProxyItem(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.domain = source["domain"];
	        this.enabled = source["enabled"];
	        this.status = source["status"];
	        this.latency = source["latency"];
	        this.speed = source["speed"];
	        this.type = source["type"];
	    }
	}
	export class ProxyRecord {
	    domain: string;
	    successCount: number;
	    totalBytes: number;
	    averageSpeed: number;
	    failCount: number;
	    // Go type: time
	    firstUsedAt: any;
	    // Go type: time
	    lastUsedAt: any;
	    speedHistory: number[];
	
	    static createFrom(source: any = {}) {
	        return new ProxyRecord(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.domain = source["domain"];
	        this.successCount = source["successCount"];
	        this.totalBytes = source["totalBytes"];
	        this.averageSpeed = source["averageSpeed"];
	        this.failCount = source["failCount"];
	        this.firstUsedAt = this.convertValues(source["firstUsedAt"], null);
	        this.lastUsedAt = this.convertValues(source["lastUsedAt"], null);
	        this.speedHistory = source["speedHistory"];
	    }
	
		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class ProxyTestResult {
	    domain: string;
	    latency: string;
	    speed: string;
	    status: string;
	
	    static createFrom(source: any = {}) {
	        return new ProxyTestResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.domain = source["domain"];
	        this.latency = source["latency"];
	        this.speed = source["speed"];
	        this.status = source["status"];
	    }
	}
	export class Settings {
	    defaultSaveDir: string;
	    defaultConcurrency: number;
	    partSize: number;
	    maxRetry: number;
	    timeout: number;
	    autoTestOnStart: boolean;
	    silentSpeedThreshold: number;
	    silentLatencyThreshold: number;
	    tcpTimeout: number;
	    testFileSize: string;
	    theme: string;
	    language: string;
	    checkUpdate: boolean;
	    enableHTTPAPI: boolean;
	    httpAPIPort: number;
	    allowRemoteAccess: boolean;
	
	    static createFrom(source: any = {}) {
	        return new Settings(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.defaultSaveDir = source["defaultSaveDir"];
	        this.defaultConcurrency = source["defaultConcurrency"];
	        this.partSize = source["partSize"];
	        this.maxRetry = source["maxRetry"];
	        this.timeout = source["timeout"];
	        this.autoTestOnStart = source["autoTestOnStart"];
	        this.silentSpeedThreshold = source["silentSpeedThreshold"];
	        this.silentLatencyThreshold = source["silentLatencyThreshold"];
	        this.tcpTimeout = source["tcpTimeout"];
	        this.testFileSize = source["testFileSize"];
	        this.theme = source["theme"];
	        this.language = source["language"];
	        this.checkUpdate = source["checkUpdate"];
	        this.enableHTTPAPI = source["enableHTTPAPI"];
	        this.httpAPIPort = source["httpAPIPort"];
	        this.allowRemoteAccess = source["allowRemoteAccess"];
	    }
	}
	export class TaskInfo {
	    id: number;
	    url: string;
	    fileName: string;
	    saveDir: string;
	    totalBytes: number;
	    downloaded: number;
	    speed: number;
	    eta: string;
	    status: string;
	    workerCount: number;
	    proxySwitchCnt: number;
	    progress: number;
	    // Go type: time
	    createdAt: any;
	
	    static createFrom(source: any = {}) {
	        return new TaskInfo(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.url = source["url"];
	        this.fileName = source["fileName"];
	        this.saveDir = source["saveDir"];
	        this.totalBytes = source["totalBytes"];
	        this.downloaded = source["downloaded"];
	        this.speed = source["speed"];
	        this.eta = source["eta"];
	        this.status = source["status"];
	        this.workerCount = source["workerCount"];
	        this.proxySwitchCnt = source["proxySwitchCnt"];
	        this.progress = source["progress"];
	        this.createdAt = this.convertValues(source["createdAt"], null);
	    }
	
		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}

}

