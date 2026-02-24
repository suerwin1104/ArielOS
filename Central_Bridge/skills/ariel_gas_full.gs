/**
 * 🤖 ArielOS v4.3 - Deepened GAS Backend (Sentinel + Sandbox Router)
 * Based on GAS_EXP.txt
 */
const CONFIG = {
    GEMINI_API_KEY: 'AIzaSyCF7n-L2GSZUCqvaH_z-4wjUtx315CKsk0',
    EXA_API_KEY: '87a47899-40ae-4084-b61a-c34dab3ab4de',
    GCS_API_KEY: 'AIzaSyALDMC2xS284lX14_lGuNDs7RPuytmWiOs',
    GCS_CX: 'f746b0b2151384a3a',
    DISCORD_WEBHOOK_URL: 'https://discord.com/api/webhooks/1474300583661011139/Y8J-25PoiCxDOfSUihMaMnUmHtKh2tarQgzUvZwgb0fJ_WIQB-R-qIME9rdCRlP7w9zn',
    SCAN_WINDOW_DAYS: 21,
    USER_NAME: 'erwin',
    TIMEZONE: "GMT+8"
};

// ==========================================
// 1. Reactive Router (Called by Ariel Bridge)
// ==========================================

function doPost(e) {
  var data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return createJsonResponse("error", "Invalid JSON payload");
  }

  var action = data.action;
  
  if (action === "search_and_filter") {
    return handleSearchAndFilter(data);
  } else if (action === "batch_execute") {
    return handleBatchExecute(data);
  } else if (action === "get_calendar_summary") {
    return handleCalendarSummary(data);
  } else if (action === "add") {
    // Basic support for adding calendar event if needed
    return createJsonResponse("error", "Action not fully implemented in this router yet.");
  }

  return createJsonResponse("error", "Unknown action: " + action);
}

function doGet(e) {
  // Agent background polling requests uses GET. We return calendar, emails, and news.
  var results = {
      schedule: getCalendarData(3),
      emails: getEmailData(5),
      news: performCloudSearch("AI technology").slice(0, 3), // Fetch recent AI news
      today: Utilities.formatDate(new Date(), CONFIG.TIMEZONE, "yyyy/MM/dd")
  };
  return createJsonResponse("success", results);
}

/**
 * Core Logic: Fetch -> Filter -> Sort (All in GAS Sandbox)
 */
function handleSearchAndFilter(params) {
  var query = params.query || "";
  var filterCode = params.filterCode || "";
  var searchType = params.searchType || "exa";
  
  // 1. Fetch Data
  var rawData;
  if(searchType === "google") {
      rawData = performGoogleSearch(query);
  } else {
      rawData = performCloudSearch(query);
  }

  
  // 2. JS Sandbox: Filter & Sort
  var processedResult;
  try {
    // Dynamic JS evaluation using Function constructor
    var sandboxFunc = new Function('data', filterCode + '; return data;');
    processedResult = sandboxFunc(rawData);
  } catch (err) {
    return createJsonResponse("error", "JS Sandbox Error: " + err.message);
  }
  
  return createJsonResponse("success", {
    query: query,
    result: processedResult
  });
}

function handleBatchExecute(params) {
  var tasks = params.tasks || [];
  var results = {};
  
  tasks.forEach(function(task) {
    if (task.action === "calendar") {
      results.calendar = getCalendarData(task.days || 3);
    } else if (task.action === "emails") {
      results.emails = getEmailData(task.limit || 5);
    } else if (task.action === "search") {
      // handleSearchAndFilter returns a TextOutput object
      var searchResOutput = handleSearchAndFilter(task.params);
      if (searchResOutput) {
          // We need to parse the content back into an object
          var contentStr = searchResOutput.getContent();
          try {
             var contentObj = JSON.parse(contentStr);
             results.search = contentObj.data || contentObj; 
          } catch(e) {
             results.search = { error: "Failed to parse search result in batch" };
          }
      }
    }
  });
  
  return createJsonResponse("success", results);
}

function performCloudSearch(query) {
    if (!query) query = "technology news";
    const url = 'https://api.exa.ai/search';
    const payload = {
      "query": query,
      "numResults": 5, // Reduced to 5 to save bandwidth/tokens since we are pulling full text
      "useAutoprompt": true,
      "contents": {
          "text": {
              "maxCharacters": 1500, // The Distillation process: Cap at 1500 chars per result
              "includeHtmlTags": false
          }
      }
    };
    
    const options = {
      "method": "post",
      "contentType": "application/json",
      "headers": { "x-api-key": CONFIG.EXA_API_KEY },
      "payload": JSON.stringify(payload),
      "muteHttpExceptions": true
    };
  
    try {
      const response = UrlFetchApp.fetch(url, options);
      const data = JSON.parse(response.getContentText());
      
      if (!data.results) return [{ title: "Exa Search Failed", cat: "ERROR", date: new Date().toISOString() }];
      
      return data.results.map(r => {
        // Data Distillation & Cleanup
        let rawText = r.text || r.summary || "No content provided by Exa.";
        let cleanText = rawText.replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim();
        
        return {
          title: r.title,
          date: r.publishedDate || new Date().toISOString(),
          url: r.url,
          cat: "NEWS",
          author: r.author || "Unknown",
          content: cleanText // The high-purity distilled text
        };
      });
    } catch(err) {
      return [{ title: "Exa Request Error: " + err.message, cat: "ERROR", date: new Date().toISOString() }];
    }
}

function performGoogleSearch(query) {
    if (!query) query = "technology news";
    
    // Google Custom Search API endpoint — Force Taiwan region and Traditional Chinese
    const url = `https://www.googleapis.com/customsearch/v1?key=${CONFIG.GCS_API_KEY}&cx=${CONFIG.GCS_CX}&q=${encodeURIComponent(query)}&num=5&gl=tw&lr=lang_zh-TW`;
    
    try {
      const response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
      const data = JSON.parse(response.getContentText());
      
      if (data.error) return [{ title: "Google Search Error: " + data.error.message, cat: "ERROR", date: new Date().toISOString() }];
      if (!data.items) return []; // No results found
      
      return data.items.map(r => {
        // Data Distillation & Cleanup for Google Snippets
        let cleanSnippet = (r.snippet || "No snippet").replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim();
        
        return {
          title: r.title,
          url: r.link,
          content: cleanSnippet, // Google's snippet is usually concise enough
          source: r.displayLink,
          cat: "GOOGLE_RES"
        };
      });
    } catch(err) {
      return [{ title: "Google Request Error: " + err.message, cat: "ERROR", date: new Date().toISOString() }];
    }
}

function getCalendarData(days) {
    const now = new Date();
    const future = new Date(now.getTime() + (days * 24 * 60 * 60 * 1000));
    let items = [];
    CalendarApp.getAllCalendars().forEach(cal => {
        try {
          cal.getEvents(now, future).forEach(e => {
              items.push({ time: Utilities.formatDate(e.getStartTime(), CONFIG.TIMEZONE, "MM/dd HH:mm"), title: e.getTitle() });
          });
        } catch(e) {}
    });
    return items;
}

function getEmailData(limit) {
    let items = [];
    try {
      // Fetch only recent unread emails (e.g., from the last 2 days) to avoid old clutter
      const threads = GmailApp.search('is:unread newer_than:2d', 0, limit);
      threads.forEach(t => {
          var rawBody = t.getMessages()[0].getPlainBody() || "";
          var cleanSnippet = rawBody.replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim().substring(0, 100);
          items.push({ 
            from: t.getMessages()[0].getFrom(), 
            subject: t.getFirstMessageSubject(), 
            snippet: cleanSnippet 
          });
      });
    } catch(e) {}
    return items;
}

function handleCalendarSummary(params) {
    return createJsonResponse("success", getCalendarData(params.days || 7));
}

function createJsonResponse(status, payload) {
  var response = { status: status };
  if (status === "success") {
      response.data = payload;
  } else {
      response.error = payload;
  }
  return ContentService.createTextOutput(JSON.stringify(response))
    .setMimeType(ContentService.MimeType.JSON);
}

// ==========================================
// 2. Proactive Sentinel (Existing logic from GAS_EXP.txt)
// ==========================================

function arielSentinel() {
    console.log("⏰ Ariel Sentinel 掃描啟動...");
    const now = new Date();
    const future = new Date(now.getTime() + (CONFIG.SCAN_WINDOW_DAYS * 24 * 60 * 60 * 1000));
    let newItems = [];

    const cache = PropertiesService.getScriptProperties();
    let sentHistory = cache.getProperty('SENT_HISTORY') || "";

    try {
        // 1. 檢查日曆
        const calendars = CalendarApp.getAllCalendars();
        calendars.forEach(cal => {
            try {
                const events = cal.getEvents(now, future);
                events.forEach(e => {
                    const itemID = `EVT_${e.getId()}_${e.getLastUpdated().getTime()}`;
                    if (sentHistory.indexOf(itemID) === -1) {
                        const timeStr = Utilities.formatDate(e.getStartTime(), CONFIG.TIMEZONE, "yyyy/MM/dd HH:mm");
                        newItems.push({ id: itemID, text: `[行程預告] ${e.getTitle()}, 時間: ${timeStr}` });
                    }
                });
            } catch (calErr) {
                console.error(`[ERROR] 日曆掃描異常: ${cal.getName()}`);
            }
        });

        // 2. 檢查 Gmail
        try {
            const threads = GmailApp.search('is:unread', 0, 5);
            threads.forEach(t => {
                const itemID = `MAIL_${t.getId()}_${t.getLastMessageDate().getTime()}`;
                if (sentHistory.indexOf(itemID) === -1) {
                    newItems.push({ id: itemID, text: `[新信通知] 寄件者: ${t.getMessages()[0].getFrom()}, 標題: ${t.getFirstMessageSubject()}` });
                }
            });
        } catch (mailErr) {
            console.error(`[ERROR] 郵件掃描異常: ${mailErr}`);
        }

        // 3. 發送通知
        if (newItems.length > 0) {
            const reportContext = newItems.map(item => item.text).join("\n");
            let arielSpeech = "";
            try {
                arielSpeech = callGeminiAI(reportContext);
            } catch (aiErr) {
                console.error(`[AI 失敗] ${aiErr.message}`);
                arielSpeech = `⚠️ AI 處理失敗\n\n原始摘要：\n` + reportContext;
            }

            sendToDiscord(arielSpeech);

            const newIDs = newItems.map(item => item.id).join(",");
            sentHistory = (sentHistory ? sentHistory + "," : "") + newIDs;
            const historyArray = sentHistory.split(",");
            if (historyArray.length > 200) {
                sentHistory = historyArray.slice(-200).join(",");
            }
            cache.setProperty('SENT_HISTORY', sentHistory);
        }
    } catch (err) {
        console.error("❌ 系統崩潰: " + err.stack);
    }
}

function callGeminiAI(content) {
    // 使用 2.5-flash 模型 (穩定免費版)
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${CONFIG.GEMINI_API_KEY}`;
    const todayStr = Utilities.formatDate(new Date(), CONFIG.TIMEZONE, "yyyy/MM/dd HH:mm");
    const prompt = `現在時間是 ${todayStr}。使用者是 ${CONFIG.USER_NAME}。請彙整以下新收到的行程與郵件，並以專業秘書 Ariel 的身分進行親切提醒（繁體中文）：\n${content}`;
    
    const payload = { "contents": [{ "parts": [{ "text": prompt }] }] };
    const options = { 
        "method": "post", 
        "contentType": "application/json", 
        "payload": JSON.stringify(payload), 
        "muteHttpExceptions": true 
    };

    const response = UrlFetchApp.fetch(url, options);
    const result = JSON.parse(response.getContentText());
    if (result.candidates && result.candidates[0].content) {
        return result.candidates[0].content.parts[0].text;
    }
    return "無法生成摘要。";
}

function sendToDiscord(message) {
    UrlFetchApp.fetch(CONFIG.DISCORD_WEBHOOK_URL, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "username": "Ariel 執行祕書", "content": message })
    });
}

function setupTrigger() {
    const triggers = ScriptApp.getProjectTriggers();
    triggers.forEach(t => {
        if (t.getHandlerFunction() === 'arielSentinel') {
            ScriptApp.deleteTrigger(t);
        }
    });

    ScriptApp.newTrigger('arielSentinel')
        .timeBased()
        .everyMinutes(10)
        .create();
    
    console.log("✅ ArielOS 觸發器部署完成。");
}
