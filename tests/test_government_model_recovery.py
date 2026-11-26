"""Exercise model failures and recovery without spending API credits."""
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect_government_news as collector
import report_government_sources as reports


def translation(text):
    return {"english_translation": text, "short_english_summary": "A short summary."}


class GovernmentModelRecoveryTests(unittest.TestCase):
    def response(self, value):
        return io.BytesIO(json.dumps(value).encode())

    def test_truncated_but_parseable_json_is_rejected(self):
        response = {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
                    "output_text": json.dumps(translation("Only the beginning"))}
        with patch.dict(os.environ, OPENAI_API_KEY="test"), patch.object(collector.urllib.request, "urlopen", return_value=self.response(response)) as call:
            with self.assertRaisesRegex(collector.ModelOutputError, "incomplete_max_output_tokens"):
                collector.ask_openai("Source", False)
        self.assertEqual(call.call_count, 1)

    def test_malformed_translation_not_repeated_five_times(self):
        response = {"status": "completed", "output_text": '{"english_translation":"unfinished'}
        with patch.dict(os.environ, OPENAI_API_KEY="test"), patch.object(collector.urllib.request, "urlopen", return_value=self.response(response)) as call:
            with self.assertRaisesRegex(collector.ModelOutputError, "invalid_json"):
                collector.ask_openai("Source", False)
        self.assertEqual(call.call_count, 1)

    def test_translation_request_has_budget_without_irrelevant_topic_taxonomy(self):
        with patch.dict(os.environ, OPENAI_API_KEY="test"), patch.object(collector.urllib.request, "urlopen", return_value=self.response({"status":"completed","output_text":json.dumps(translation("Hello"))})) as call:
            collector.ask_openai("Source", False)
        request=json.loads(call.call_args.args[0].data)
        self.assertEqual(request["max_output_tokens"],8192)
        self.assertNotIn("Topic codes and meanings",request["input"][0]["content"])

    def test_refusal_does_not_trigger_smaller_repeated_requests(self):
        response={"status":"completed","output":[{"content":[{"type":"refusal","refusal":"No"}]}]}
        with patch.dict(os.environ, OPENAI_API_KEY="test"), patch.object(collector.urllib.request,"urlopen",return_value=self.response(response)) as call:
            with self.assertRaisesRegex(collector.ModelOutputError,"model_refusal"):
                collector.translate_document("Source "*500)
        self.assertEqual(call.call_count,1)

    def test_one_http_400_is_deferred_with_safe_error_code(self):
        body=io.BytesIO(json.dumps({"error":{"code":"invalid_prompt","message":"private source text"}}).encode())
        denied=urllib.error.HTTPError("https://api.openai.com/v1/responses",400,"Bad Request",{},body)
        with patch.dict(os.environ,OPENAI_API_KEY="test"),patch.object(collector.urllib.request,"urlopen",side_effect=denied) as call:
            with self.assertRaisesRegex(collector.ModelRequestError,"http_400_invalid_prompt") as caught:
                collector.ask_openai("Source",False)
        self.assertNotIn("private source text",str(caught.exception))
        self.assertEqual(call.call_count,1)

    def test_long_translation_splits_without_losing_source(self):
        text=" ".join(f"word{i}" for i in range(2400))
        accepted=[]
        def model(chunk,*args,**kwargs):
            if len(chunk)>3000:
                raise collector.ModelOutputError("invalid_json",splittable=True)
            if chunk.lstrip().startswith("word"): accepted.append(chunk)
            return translation(chunk)
        with patch.object(collector,"ask_openai",side_effect=model),contextlib.redirect_stdout(io.StringIO()):
            result,summary=collector.translate_document(text)
        self.assertEqual(result.split(),text.split())
        self.assertEqual(" ".join(accepted).split(),text.split())
        self.assertLessEqual(len(summary.split()),45)

    def test_rate_limit_reuses_completed_chunks_and_invalidates_changed_source(self):
        checkpoint={}; calls=[]
        text="a"*6000+"b"*6000
        def model(chunk,*args,**kwargs):
            calls.append(chunk)
            if chunk.startswith("b"): raise collector.ModelRateLimit("rate_limit_exceeded")
            return translation(chunk)
        with patch.object(collector,"ask_openai",side_effect=model),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(collector.ModelRateLimit): collector.translate_document(text,checkpoint)
        self.assertEqual(len(checkpoint),1)
        with patch.object(collector,"ask_openai",side_effect=lambda chunk,*args,**kwargs: translation(chunk)) as call,contextlib.redirect_stdout(io.StringIO()):
            translated,_=collector.translate_document(text,checkpoint)
            self.assertNotIn("a"*6000,[c.args[0] for c in call.call_args_list])
            self.assertEqual(translated.replace("\n",""),text)
            collector.translate_document("changed source",checkpoint)
            self.assertEqual(call.call_args.args[0],"changed source")

    def test_summary_stage_accepts_summary_without_redundant_translation(self):
        text="a"*6000+"b"*1409
        outputs=[translation("First translated section."),translation("Second translated section."),
                 {"short_english_summary":"Both sections summarized."}]
        responses=[self.response({"status":"completed","output_text":json.dumps(output)}) for output in outputs]
        checkpoint={}
        with patch.dict(os.environ,OPENAI_API_KEY="test"),patch.object(collector.urllib.request,"urlopen",side_effect=responses) as call,contextlib.redirect_stdout(io.StringIO()):
            translated,summary=collector.translate_document(text,checkpoint)
            self.assertEqual(translated,"First translated section.\nSecond translated section.")
            self.assertEqual(summary,"Both sections summarized.")
            summary_request=json.loads(call.call_args.args[0].data)
            self.assertEqual(summary_request["text"]["format"]["schema"]["required"],["short_english_summary"])
            self.assertNotIn("Topic codes and meanings",summary_request["input"][0]["content"])
            self.assertEqual(collector.translate_document(text,checkpoint),(translated,summary))
            self.assertEqual(call.call_count,3)

    def test_failed_summary_reuses_translations_on_next_pass(self):
        text="a"*6000+"b"*1409; checkpoint={}
        with patch.object(collector,"ask_openai",side_effect=[translation("First."),translation("Second."),collector.ModelOutputError("empty_summary")]),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(collector.ModelOutputError,"empty_summary"):
                collector.translate_document(text,checkpoint)
        with patch.object(collector,"ask_openai",return_value={"short_english_summary":"Recovered summary."}) as call,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collector.translate_document(text,checkpoint),("First.\nSecond.","Recovered summary."))
            call.assert_called_once_with("A short summary.\nA short summary.",False,summary_only=True)

    def test_overlong_summary_is_shortened_without_retranslating(self):
        text="a"*6000+"b"*1409; checkpoint={}; overlong="word "*60
        outputs=[translation("First."),translation("Second."),
                 {"short_english_summary":overlong},{"short_english_summary":"Concise summary."}]
        with patch.object(collector,"ask_openai",side_effect=outputs) as call,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collector.translate_document(text,checkpoint),("First.\nSecond.","Concise summary."))
            self.assertEqual(call.call_count,4)
            call.assert_called_with(overlong,False,summary_only=True)

    def test_summary_shortening_has_a_fixed_retry_limit(self):
        outputs=[translation("First."),translation("Second.")]+[{"short_english_summary":"word "*60}]*3
        with patch.object(collector,"ask_openai",side_effect=outputs) as call,contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(collector.ModelOutputError,"summary_exceeds_45_words"):
                collector.translate_document("a"*6000+"b"*1409)
            self.assertEqual(call.call_count,5)

    def test_source_bound_summary_requires_exact_article_bytes(self):
        source="Official release text"
        item={"id":"reviewed-id","url":"https://www.canada.ca/en/example.html"}
        override={"id":"reviewed-id","url":item["url"],
                  "source_sha256":hashlib.sha256(source.encode()).hexdigest(),
                  "short_english_summary":"A concise, source-checked summary."}
        self.assertEqual(collector.source_bound_summary_override(item,source,{item["id"]:override}),override["short_english_summary"])
        self.assertIsNone(collector.source_bound_summary_override(item,source+" changed",{item["id"]:override}))
        self.assertIsNone(collector.source_bound_summary_override({**item,"url":item["url"]+"?changed"},source,{item["id"]:override}))

    def test_source_bound_summary_preserves_full_translation_without_resummarizing(self):
        with patch.object(collector,"ask_openai",return_value={"english_translation":"Complete translated source.","short_english_summary":"word "*60}) as call:
            self.assertEqual(collector.translate_document("Official source",source_bound_summary="Verified concise summary."),
                             ("Complete translated source.","Verified concise summary."))
            call.assert_called_once_with("Official source",False)

    def test_china_attachment_must_match_reviewed_document(self):
        opening="JOINT STATEMENT BETWEEN THE PEOPLE’S REPUBLIC OF CHINA AND THE REPUBLIC OF BOTSWANA"
        closing="Following their meeting, the two Presidents witnessed the signing of bilateral cooperation documents in various fields."
        statement=opening+"\r"+("The countries agreed on global AI governance and security cooperation. "*300)+closing
        document=bytes.fromhex("d0cf11e0a1b11ae1")+b"\0"*16+statement.encode("utf-16le")
        html=("<div class='Artical_Content'>Please see the attachment for the full text. "
              "<a href='//english.www.gov.cn/atts/stream/files/6ace3291c6d0c78809900175'>Full statement</a></div>").encode()
        item={"country_code":"CN","url":collector.CHINA_BOTSWANA_STATEMENT_URL}
        with patch.object(collector,"CHINA_BOTSWANA_ATTACHMENT_SHA256",hashlib.sha256(document).hexdigest()),patch.object(collector,"fetch",side_effect=[(item["url"],html),(collector.CHINA_BOTSWANA_ATTACHMENT_URL,document)]) as fetch:
            article=collector.article_text(item)
            self.assertIn("global AI governance",article)
            self.assertTrue(article.endswith(closing))
            self.assertEqual(fetch.call_count,2)
        with self.assertRaisesRegex(RuntimeError,"changed since source review"):
            collector.extract_china_botswana_statement(document)

    def test_requeue_only_unreviewed_china_attachment_error(self):
        item={"id":"c20b880177123988076f","url":collector.CHINA_BOTSWANA_STATEMENT_URL,
              "classification_status":"needs_review","classification_error":"RuntimeError"}
        self.assertFalse(collector.requeue_reviewed_attachment({**item,"human_reviewed":True}))
        self.assertFalse(collector.requeue_reviewed_attachment({**item,"url":"https://other.example"}))
        self.assertFalse(collector.requeue_reviewed_attachment({**item,"classification_error":"ModelOutputError"}))
        self.assertTrue(collector.requeue_reviewed_attachment(item))
        self.assertEqual(item["classification_status"],"pending_classification")
        self.assertNotIn("classification_error",item)

    def test_one_rejected_item_does_not_block_publication_or_publish_private_chunks(self):
        records=[{"id":str(i),"url":f"https://example.gov/{i}","country_code":"BA","country":"Bosnia and Herzegovina","title":"News","published_at":"2026-10-29T10:00:00+00:00","classification_status":"pending_classification"} for i in range(2)]
        # canonical_government_items uses URL-based IDs; match its processing order.
        records=list(collector.canonical_government_items(records).values())
        records.sort(key=lambda r:hashlib.sha256(r["id"].encode()).hexdigest())
        labels={"relevance":"not_related","topics":[],"roles":[],"viewpoints":[]}
        def translate(text,checkpoint,on_progress):
            checkpoint["private"] = translation("PRIVATE TRANSLATION")
            on_progress()
            if text==records[1]["url"]: raise collector.ModelRequestError("http_400_invalid_prompt")
            return "English text","Summary"
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/"state.json"; public=root/"government-data.json"
            state.write_text(json.dumps({"items":records,"calibration_complete":True}))
            with patch.multiple(collector,STATE=state,PUBLIC=public,CORRECTIONS=root/"none.json",REVIEW_QUEUE=root/"review.json"),patch.object(sys,"argv",["collector","--classify-only"]),patch.object(collector,"article_text",side_effect=lambda item:item["url"]),patch.object(collector,"translate_document",side_effect=translate),patch.object(collector,"ask_openai",return_value=labels),contextlib.redirect_stdout(io.StringIO()):
                collector.main()
            saved={r["id"]:r for r in json.loads(state.read_text())["items"]}
            self.assertEqual(saved[records[0]["id"]]["classification_status"],"provisional")
            self.assertNotIn("translation_checkpoint",saved[records[0]["id"]])
            self.assertEqual(saved[records[1]["id"]]["classification_status"],"needs_review")
            self.assertIn("translation_checkpoint",saved[records[1]["id"]])
            self.assertNotIn("PRIVATE TRANSLATION",public.read_text())
            self.assertNotIn("translation_checkpoint",public.read_text())
            report=json.loads((root/"government-source-diagnostics.json").read_text())
            self.assertEqual(len(report["model_failures"]),1)
            self.assertEqual(report["model_failures"][0]["error"],"http_400_invalid_prompt")
            self.assertIn("Model processing deferred 1",reports.summary(report))

    def test_missing_source_model_answer_is_withheld_and_queued(self):
        record={"url":"https://example.gov/attachment", "country_code":"BA",
                "country":"Bosnia and Herzegovina", "title":"Official notice",
                "published_at":"2026-10-29T10:00:00+00:00",
                "classification_status":"pending_classification"}
        record=list(collector.canonical_government_items([record]).values())[0]
        labels={"relevance":"unclear", "topics":[], "roles":[],
                "confidence":0, "ticker_message":"No press release text was provided to classify.",
                "short_rationale":"No press release or translated article is included."}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/"state.json";public=root/"government-data.json"
            state.write_text(json.dumps({"items":[record],"calibration_complete":True}))
            with patch.multiple(collector,STATE=state,PUBLIC=public,CORRECTIONS=root/"none.json",REVIEW_QUEUE=root/"review.json"),patch.object(sys,"argv",["collector","--classify-only"]),patch.object(collector,"article_text",return_value="Die Pressemitteilung finden Sie im Anhang."),patch.object(collector,"translate_document",return_value=("The press release is attached.","The press release is attached.")),patch.object(collector,"ask_openai",return_value=labels),contextlib.redirect_stdout(io.StringIO()):
                collector.main()
            item=json.loads(public.read_text())["items"][0]
            self.assertEqual(item["classification_status"],"source_incomplete")
            self.assertNotIn("ticker_message",item)
            self.assertNotIn("english_summary",item)
            self.assertEqual(json.loads((root/"review.json").read_text())["items"][0]["id"],record["id"])

    def test_repeated_http_400_without_success_fails_instead_of_reporting_green(self):
        records=[{"id":str(i),"url":f"https://example.gov/{i}","country_code":"BA","country":"Bosnia and Herzegovina","title":"News","published_at":"2026-10-29T10:00:00+00:00","classification_status":"pending_classification"} for i in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/"state.json"
            state.write_text(json.dumps({"items":records,"calibration_complete":True}))
            with patch.multiple(collector,STATE=state,PUBLIC=root/"public.json",CORRECTIONS=root/"none.json",REVIEW_QUEUE=root/"review.json"),patch.object(sys,"argv",["collector","--classify-only"]),patch.object(collector,"article_text",return_value="Source"),patch.object(collector,"translate_document",side_effect=collector.ModelRequestError("http_400_invalid_prompt")),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,"Three model requests rejected"):
                    collector.main()
            saved=json.loads(state.read_text())["items"]
            self.assertEqual(len(saved),3)
            self.assertTrue(all(item["classification_status"]=="needs_review" for item in saved))

    def test_network_reset_retries_and_http_denial_remains_visible(self):
        reset=urllib.error.URLError(ConnectionResetError("Connection reset by peer"))
        with patch.object(collector,"_fetch_once",side_effect=[reset,("url",b"page")]) as call,patch.object(collector.time,"sleep"):
            self.assertEqual(collector.fetch("url"),("url",b"page"))
            self.assertEqual(call.call_count,2)
        with patch.object(collector,"_fetch_once",side_effect=urllib.error.HTTPError("url",403,"Denied",{},None)) as call:
            with self.assertRaises(urllib.error.HTTPError):collector.fetch("url")
            self.assertEqual(call.call_count,1)

    def test_czech_office_events_and_press_releases_are_official_but_external_hosts_rejected(self):
        country={"url":"https://vlada.gov.cz/scripts/detail.php?pgid=1305","name":"Czechia"}
        article="https://vlada.gov.cz/cz/urad-vlady/akce/strakova-akademie-229507/"
        def page(url):return f'<div class="list__item"><div class="post__date"><p>28. 10. 2026</p></div><a href="{url}" class="post__link">Official event</a>'.encode()
        start=dt.datetime(2026,10,28,tzinfo=collector.PRAGUE);end=start+dt.timedelta(days=1)
        with patch.object(collector,"fetch",return_value=(country["url"],page(article))):
            items,_=collector.discover_czechia(country,start,end)
            self.assertEqual(items[0]["url"],article)
        press="https://vlada.gov.cz/cz/media-centrum/tiskove-zpravy/official-229507/"
        with patch.object(collector,"fetch",return_value=(country["url"],page(press))):
            items,_=collector.discover_czechia(country,start,end)
            self.assertEqual(items[0]["url"],press)
        with patch.object(collector,"fetch",return_value=(country["url"],page(article.replace("vlada.gov.cz/","vlada.gov.cz.evil.example/")))):
            with self.assertRaisesRegex(RuntimeError,"Unexpected Czech"):
                collector.discover_czechia(country,start,end)


if __name__ == "__main__": unittest.main()
