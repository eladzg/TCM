// Hebrew for the Chinese text the interview prototype shows, and links to the source each string came
// from. Translations come from app/interview/he_dict.js (built by tools/treatment/build_he.py from
// kb/translations/he); they are drafts for clinician review, so the page keeps the Chinese next to them.
(function (root) {
  "use strict";

  var D = root.TCM_HE || {};

  var BOOKS = {
    "傷寒論": "שאנג האן לון",
    "金匱要略": "ג'ין גוויי יאו לואה",
    "本草備要": "בן צאו ביי יאו",
    "针灸大成": "ג'ן ג'יו דא צ'נג",
    "針灸大成": "ג'ן ג'יו דא צ'נג",
    "醫方集解": "יי פאנג ג'י ג'יה"
  };

  var NUM = "一二三四五六七八九十";
  // Chapter titles of the classics, as cited in the source references.
  var CHAPTERS = {
    "辨太陽病脈證並治（上）": "מחלות טאי-יאנג, חלק א", "辨太陽病脈證並治（中）": "מחלות טאי-יאנג, חלק ב",
    "辨太陽病脈證並治（下）": "מחלות טאי-יאנג, חלק ג", "辨陽明病脈證並治": "מחלות יאנג-מינג",
    "辨少陽病脈證並治": "מחלות שאו-יאנג", "辨太陰病脈證並治": "מחלות טאי-יין", "辨少陰病脈證並治": "מחלות שאו-יין",
    "辨厥陰病脈證並治": "מחלות ג'ואה-יין", "辨霍亂病脈證並治": "כולרה (הואו לואן)",
    "辨陰陽易差後勞復病脈證並治": "הדבקה בין יין ליאנג והישנות אחרי החלמה",
    "痙濕暍病脈證並治": "עוויתות, לחות ומכת חום", "百合病狐惑陰陽毒病脈證並治": "מחלת באי-חה, חו-חואו ורעל יין-יאנג",
    "瘧病脈證並治": "קדחת לסירוגין", "中風歷節病脈證並治": "שבץ רוח וכאב מפרקים נודד",
    "血痹虛勞病脈證並治": "חסימת דם ותשישות", "肺痿肺癰咳嗽上氣病脈證並治": "התנוונות ריאה, מורסת ריאה, שיעול וצ'י עולה",
    "奔豚氣病脈證並治": "צ'י החזיר הדוהר", "胸痹心痛短氣病脈證並治": "חסימת חזה, כאב לב וקוצר נשימה",
    "嘔吐噦下利病脈證並治": "הקאה, שיהוק ושלשול", "瘡癰腸癰浸淫病脈證並治": "פצעים, מורסות, מורסת מעי ופריחה מתפשטת",
    "跗蹶手指臂腫轉筋陰狐疝蚘蟲病脈證並治": "נפילת כף הרגל, נפיחות היד, התכווצויות, שבר ותולעים",
    "婦人妊娠病脈證並治": "מחלות היריון", "水氣病脈證並治": "מחלות מים (בצקות)",
    // 醫方集解: the 21 categories of formulas, as printed on Wikisource
    "补养之劑": "מרשמים מחזקים ומזינים", "发表之劑": "מרשמים לשחרור החיצוני", "涌吐之劑": "מרשמים מעוררי הקאה",
    "攻里之劑": "מרשמים לתקיפת הפנים (משלשלים)", "表里之劑": "מרשמים לחיצוני ולפנימי יחד", "和解之劑": "מרשמים מרמנים ומפשרים",
    "理气之劑": "מרשמים לוויסות הצ'י", "理血之劑": "מרשמים לוויסות הדם", "祛风之劑": "מרשמים לסילוק רוח",
    "祛寒之劑": "מרשמים לסילוק קור", "清暑之劑": "מרשמים לקירור חום הקיץ", "利湿之劑": "מרשמים לניקוז לחות",
    "润燥之劑": "מרשמים להרטבת יובש", "瀉火之劑": "מרשמים להורדת אש", "除痰之劑": "מרשמים לסילוק ליחה",
    "消导之劑": "מרשמים לעיכול ולהורדת מזון תקוע", "收涩之劑": "מרשמים מכווצים ומייצבים", "杀虫之劑": "מרשמים נגד תולעים",
    "明目之劑": "מרשמים להבהרת העיניים", "痈疡之劑": "מרשמים למורסות וכיבים", "經产之劑": "מרשמים למחזור וללידה"
  };
  var SECTIONS = { "草部": "צמחי עשב", "木部": "עצים", "果部": "פירות", "穀菜部": "דגנים וירקות", "金石水土部": "מתכות, אבנים, מים ואדמה",
                   "禽獸部": "עופות ובהמות", "鱗介魚蟲部": "בעלי קשקשים, צדפות, דגים וחרקים", "人部": "מן האדם" };
  function chinese(n) {   // 十七 -> 17, 二十 -> 20, 五 -> 5
    var t = n.indexOf("十");
    if (t === -1) return NUM.indexOf(n) + 1;
    return (t === 0 ? 1 : NUM.indexOf(n[0]) + 1) * 10 + (n[t + 1] ? NUM.indexOf(n[t + 1]) + 1 : 0);
  }
  var GUT = "https://www.gutenberg.org/cache/epub/";
  var SOURCES = [
    { re: /^WS-ZJDC (卷\S+)/, url: function (m) { return "https://zh.wikisource.org/wiki/" + encodeURI("針灸大成/" + m[1]); }, frag: true, he: "ג'ן ג'יו דא צ'נג (ויקיטקסט)" },
    { re: /^WS-ZJDC/, url: function () { return "https://zh.wikisource.org/wiki/" + encodeURI("針灸大成"); }, frag: true, he: "ג'ן ג'יו דא צ'נג (ויקיטקסט)" },
    { re: /^WS-JINGUI/, url: function () { return "https://zh.wikisource.org/wiki/" + encodeURI("金匱要略"); }, frag: true, he: "ג'ין גוויי יאו לואה (ויקיטקסט)" },
    { re: /^WS-YFJJ/, url: function () { return "https://zh.wikisource.org/wiki/" + encodeURI("醫方集解"); }, frag: true, he: "יי פאנג ג'י ג'יה (ויקיטקסט)" },
    { re: /^GUT-SHANGHAN/, url: function () { return GUT + "24272/pg24272-images.html"; }, frag: true, he: "שאנג האן לון (פרויקט גוטנברג)" },
    { re: /^GUT-BENCAO-BEIYAO/, url: function () { return GUT + "26888/pg26888-images.html"; }, frag: true, he: "בן צאו ביי יאו (פרויקט גוטנברג)" },
    { re: /^ACUATLAS/, url: function () { return "https://acupointatlas.com/it/dataset/"; }, he: "AcuAtlas" },
    { re: /^WHO-ISTTCM-2022/, url: function () { return "https://www.who.int/publications/i/item/9789240042322"; }, he: "WHO 2022" },
    { re: /^GBT-16751-2|^GB\/T/, url: function () { return "https://www.gov.cn/zhengce/zhengceku/2020-11/24/5563703/files/88c97a96b5ea4ae999f3a8e5f09d35d9.docx"; }, he: "GB/T 16751.2 (קובץ Word)" }
  ];

  // Hebrew for a Chinese string, or "" when there is none.
  function he(zh) {
    if (!zh) return "";
    if (D[zh]) return D[zh];
    var m = /^(十八反|十九畏): (\S+) (反|畏) (\S+)/.exec(zh);
    if (m) {
      return (m[1] === "十八反" ? "שמונה-עשר הניגודים" : "תשע-עשרה הרתיעות") + ": " + (D[m[2]] || m[2]) +
        (m[3] === "反" ? " מנוגד ל" : " נרתע מ") + (D[m[4]] || m[4]) + ", אין לשלב במרשם";
    }
    return BOOKS[zh] || "";
  }

  // Hebrew if there is one, else the original.
  function heOr(zh) { return he(zh) || zh; }

  // Hebrew name of a classic named inside a string ("傷寒論 條21" -> "שאנג האן לון סעיף 21").
  function books(s) {
    return String(s || "").replace(/傷寒論|金匱要略|本草備要|针灸大成|針灸大成|醫方集解/g, function (b) { return BOOKS[b]; })
      .replace(/條(\d+)/g, "סעיף $1").replace(/篇(\d+)\.(\d+)/g, "פרק $1 סעיף $2")
      .replace(/卷(\S)/g, function (x, n) { return "כרך " + (NUM.indexOf(n) + 1); }).replace(/考正穴法/g, "בירור מיקומי הנקודות")
      .replace(/line (\d+)/g, "שורה $1").replace(/\(([\u4e00-\u9fff]+)\)/g, function (x, z) { return D[z] ? "(" + D[z] + ")" : x; })
      .replace(/^WS-ZJDC /, "ג'ן ג'יו דא צ'נג ").replace(/^GUT-SHANGHAN /, "שאנג האן לון ").replace(/^WS-JINGUI /, "ג'ין גוויי יאו לואה ")
      .replace(/^GUT-BENCAO-BEIYAO /, "בן צאו ביי יאו ").replace(/^WS-YFJJ /, "יי פאנג ג'י ג'יה ")
      .replace(/, list cut short in this transcription/g, ", רשימת הרכיבים קטועה בתעתיק הזה")
      .replace(/([\u4e00-\u9fff（）]+?)第([一二三四五六七八九十]+)/g, function (x, c, n) { return (CHAPTERS[c] || c) + " (פרק " + chinese(n) + ")"; })
      .replace(/([\u4e00-\u9fff]+部)·([\u4e00-\u9fff]+)/g, function (x, sec, h) { return (SECTIONS[sec] || sec) + " · " + (D[h] || h); })
      .replace(/\)·([\u4e00-\u9fff]+)/g, function (x, f) { return ") · " + (D[f] || f); })
      .replace(/, after /g, ", אחרי ");
  }

  // The longest run of the quote without punctuation or an illegible □: a text fragment must match
  // the page exactly, and the pages put markup or other punctuation between sentences.
  function fragment(quote) {
    return String(quote).split(/[□。，、；：！？,;:\s]+/).reduce(function (a, b) { return b.length > a.length ? b : a; }, "");
  }

  // {url, he} for a source reference such as "WS-ZJDC 卷九 考正穴法, line 59"; quote (as printed in
  // the source) becomes a text fragment, so the browser scrolls to it and highlights it.
  function source(ref, quote) {
    ref = ref || "";
    for (var i = 0; i < SOURCES.length; i++) {
      var m = SOURCES[i].re.exec(ref);
      if (!m) continue;
      var url = SOURCES[i].url(m);
      if (quote && SOURCES[i].frag) url += "#:~:text=" + encodeURIComponent(fragment(quote));
      return { url: url, he: SOURCES[i].he };
    }
    return null;
  }

  root.TCMI18n = { he: he, heOr: heOr, books: books, source: source, BOOKS: BOOKS };
})(typeof window !== "undefined" ? window : this);
