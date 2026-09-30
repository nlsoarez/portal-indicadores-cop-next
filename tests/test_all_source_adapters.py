import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

NS="http://schemas.openxmlformats.org/spreadsheetml/2006/main"


class AllSourceAdaptersTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); os.environ["COP_PORTAL_DB"]=str(Path(self.tmp.name)/"portal.db")
        from src.infrastructure import database
        database.DB_PATH=Path(os.environ["COP_PORTAL_DB"])
        from src.infrastructure.database import initialize_database
        from src.config.seed import seed_foundation
        initialize_database(); seed_foundation()
        from src.application.access_service import AccessService
        from src.infrastructure.repositories import UserRepository
        users=UserRepository(); self.users=users; self.ctx=AccessService(users).context(users.get_by_login("ADMIN").id)
        from src.infrastructure.repositories import SegmentRepository
        self.enterprise=SegmentRepository().get_by_slug("empresarial")

    def tearDown(self): self.tmp.cleanup()

    @staticmethod
    def xlsx(df,sheet,startrow=0):
        b=io.BytesIO()
        with pd.ExcelWriter(b,engine="openpyxl") as w: df.to_excel(w,sheet_name=sheet,index=False,startrow=startrow)
        return b.getvalue()

    def test_residential_multi_indicator_parser_and_global_upload(self):
        from src.application.upload_service import UploadProcessingService
        from src.infrastructure.repositories import IndicatorRepository, SegmentRepository, UserRepository
        df=pd.DataFrame({
            "INDICADOR_NOME_ICG":["ETIT GPON","ETIT GPON","ASSERTIVIDADE ACIONAMENTO GPON","ETIT GPON"],
            "VOLUME":[2,1,4,9],"INDICADOR":[1,0,1,1],"IN_REGIONAL":["Leste"]*4,
            "DT_INICIO":["2026-09-28","2026-09-28","2026-09-29","2026-09-29"],"ANOMES":[202609]*4,
            "LOGIN_PRIMEIRO_ACIONAMENTO":["F104752","F104752","F104752","EXTERNO"],
        })
        results=UploadProcessingService().process_global_source(self.ctx,"residential_indicators","res.xlsx",self.xlsx(df,"Analitico"))
        self.assertEqual({"res_etit_gpon","res_assert_gpon"},{r.indicator_key for _,r in results})
        users=UserRepository(); seg=SegmentRepository().get_by_slug("residencial"); marcelo=users.get_by_login("F104752")
        rows=IndicatorRepository().monthly_summary_for_user(seg.id,marcelo.id)
        etit=next(r for r in rows if r["indicator_key"]=="res_etit_gpon")
        self.assertEqual(66.7,etit["value"]); self.assertEqual(3,etit["volume"])

    def test_enterprise_etit_parser(self):
        from src.application.upload_service import UploadProcessingService
        df=pd.DataFrame({"INDICADOR_NOME":["ETIT POR EVENTO"]*3,"LOGIN_ACIONAMENTO":["N0189105","N0189105","OUT"],"VOLUME":[2,1,9],"INDICADOR":[1,0,1],"IN_REGIONAL":["Leste"]*3,"DT_INICIO":["2026-09-28","2026-09-28","2026-09-28"],"ANOMES":[202609]*3})
        results=UploadProcessingService().process_global_source(self.ctx,"enterprise_indicators","emp.xlsx",self.xlsx(df,"Empresarial"))
        self.assertEqual(["emp_etit_event"],[r.indicator_key for _,r in results])
        self.assertEqual(3,results[0][1].total_volume)

    def test_chat_parser_preserves_in_group_breakdown_for_analyst(self):
        from src.application.upload_service import UploadProcessingService
        from src.infrastructure.repositories import IndicatorRepository

        df = pd.DataFrame(
            {
                "FECHAMENTO_COPREDE_LOGIN_ANALISTA": ["N0189105", "N0189105"],
                "ABERTURA_ANOMES": [202609, 202609],
                "INDICADOR_TMA_DENTRO": [1, 0],
                "CHAT_INICIO": ["2026-09-29 22:10:00", "2026-09-29 22:20:00"],
                "IN_GRUPO": ["Minas Gerais", "Minas Gerais"],
                "ABERTURA_HORA": [22, 22],
            }
        )

        UploadProcessingService().process_global_source(
            self.ctx,
            "chat_toa",
            "chat.xlsx",
            self.xlsx(df, "Analítico CHAT TOA", 3),
        )

        igor = self.users.get_by_login("N0189105")
        payload = IndicatorRepository().dashboard_payload(self.enterprise.id, igor.id)
        groups = [
            row
            for row in payload["breakdowns"]
            if row["indicator_key"] == "chat_10m"
            and row["dimension"] == "group"
        ]

        self.assertEqual(1, len(groups))
        self.assertEqual("Minas Gerais", groups[0]["dimension_value"])
        self.assertEqual(2, groups[0]["volume"])
        self.assertEqual(1, groups[0]["successes"])

    def test_productivity_parser_routes_three_segments(self):
        from src.application.upload_service import UploadProcessingService
        df=pd.DataFrame({"USUARIO_LOGIN":["F104752","N0189105","N5604148"],"DATA":["2026-09-29"]*3,"ANOMES":[202609]*3,"VOL_TOTAL":[30,40,50]})
        results=UploadProcessingService().process_global_source(self.ctx,"productivity","prod.xlsx",self.xlsx(df,"Analítico Produtividade 2026",10))
        self.assertEqual({"residencial","empresarial","preventiva"},{slug for slug,_ in results})
        self.assertTrue(all(r.indicator_key=="productivity_avg_daily" for _,r in results))

    def test_toa_upload_processes_validation_and_cancelled_in_one_file(self):
        from src.application.upload_service import UploadProcessingService
        df=pd.DataFrame({
            "INDICADOR_NOME":["TEMPO DE VALIDAÇÃO DO FORMULÁRIO","TAREFAS CANCELADAS","TAREFAS CANCELADAS"],
            "LOGIN":["N0158974","N0158974","N0158974"],"INDICADOR":[1,1,0],"ANOMES":[202609]*3,
            "IN_REGIONAL":["Leste"]*3,"DATA":["2026-09-29"]*3,
        })
        results=UploadProcessingService().process_global_source(self.ctx,"toa_indicators","toa.xlsx",self.xlsx(df,"TOA"))
        self.assertEqual({"validacao_20m","toa_cancellation_rate"},{r.indicator_key for _,r in results})

    def test_dpa_pivot_parser(self):
        from src.application.upload_service import UploadProcessingService
        definition=f'''<?xml version="1.0" encoding="UTF-8"?><pivotCacheDefinition xmlns="{NS}"><cacheFields count="5"><cacheField name="USUARIO_LOGIN"><sharedItems><s v="F104752"/></sharedItems></cacheField><cacheField name="ANOMES"><sharedItems><n v="202609"/></sharedItems></cacheField><cacheField name="DATA"><sharedItems/></cacheField><cacheField name="TEMPO_USO_SEC"/><cacheField name="HORARIO_JORNADA_SEC"/></cacheFields></pivotCacheDefinition>'''
        records=f'''<?xml version="1.0" encoding="UTF-8"?><pivotCacheRecords xmlns="{NS}" count="2"><r><x v="0"/><x v="0"/><d v="2026-09-28T00:00:00"/><n v="75"/><n v="100"/></r><r><x v="0"/><x v="0"/><d v="2026-09-29T00:00:00"/><n v="100"/><n v="100"/></r></pivotCacheRecords>'''
        raw=self._pivot(definition,records,2)
        results=UploadProcessingService().process_global_source(self.ctx,"dpa","dpa.xlsx",raw)
        residential=[r for slug,r in results if slug=="residencial"][0]
        self.assertEqual("2026-09-29",residential.data_through); self.assertEqual(200,residential.total_volume)

    def test_closing_pivot_parser(self):
        from src.application.upload_service import UploadProcessingService
        definition=f'''<?xml version="1.0" encoding="UTF-8"?><pivotCacheDefinition xmlns="{NS}"><cacheFields count="7"><cacheField name="LOGIN_VALIDOU_FECHAMENTO"><sharedItems><s v="N0189105"/></sharedItems></cacheField><cacheField name="TURNO"><sharedItems><s v="Madrugada"/></sharedItems></cacheField><cacheField name="ANOMES"><sharedItems><n v="202609"/></sharedItems></cacheField><cacheField name="VOLUME"/><cacheField name="FECHAMENTO_ASSERTIVO"/><cacheField name="IN_REGIONAL"><sharedItems><s v="Leste"/></sharedItems></cacheField><cacheField name="DIA"><sharedItems><n v="29"/></sharedItems></cacheField></cacheFields></pivotCacheDefinition>'''
        records=f'''<?xml version="1.0" encoding="UTF-8"?><pivotCacheRecords xmlns="{NS}" count="1"><r><x v="0"/><x v="0"/><x v="0"/><n v="10"/><n v="8"/><x v="0"/><x v="0"/></r></pivotCacheRecords>'''
        raw=self._pivot(definition,records,1)
        results=UploadProcessingService().process_global_source(self.ctx,"closing_toa_sir","fech.xlsx",raw)
        enterprise=[r for slug,r in results if slug=="empresarial"][0]
        self.assertEqual(10, enterprise.total_volume)
        self.assertEqual("2026-09-29", enterprise.data_through)

        from src.infrastructure.repositories import IndicatorRepository
        igor = self.users.get_by_login("N0189105")
        rows = IndicatorRepository().results_for_user(self.enterprise.id, igor.id)
        closing = next(row for row in rows if row["indicator_key"] == "closing_assertiveness")
        self.assertEqual(80.0, closing["value"])
        self.assertEqual(10, closing["volume"])

    def test_same_event_date_can_exist_in_different_competence_months(self):
        from src.infrastructure.repositories import IndicatorRepository, SegmentRepository, UserRepository

        indicators = IndicatorRepository()
        users = UserRepository()
        segment = SegmentRepository().get_by_slug("residencial")
        marcelo = users.get_by_login("F104752")
        definition = indicators.get_definition(segment.id, "productivity_avg_daily")
        login_map = {"F104752": marcelo.id}

        indicators.replace_results_for_months(
            segment_id=segment.id,
            indicator_definition_id=int(definition["id"]),
            login_to_user_id=login_map,
            rows=({"login":"F104752","period":"2026-08-31","data_month":"2026-08","value":10,"volume":1},),
            months=("2026-08",),
        )
        indicators.replace_results_for_months(
            segment_id=segment.id,
            indicator_definition_id=int(definition["id"]),
            login_to_user_id=login_map,
            rows=({"login":"F104752","period":"2026-08-31","data_month":"2026-09","value":20,"volume":1},),
            months=("2026-09",),
        )

        rows = [
            row for row in indicators.results_for_user(segment.id, marcelo.id)
            if row["indicator_key"] == "productivity_avg_daily" and row["period"] == "2026-08-31"
        ]
        self.assertEqual(2, len(rows))
        self.assertEqual({"2026-08", "2026-09"}, {row["data_month"] for row in rows})

    @staticmethod
    def _pivot(definition,records,n):
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"xl/pivotCache/pivotCacheDefinition{n}.xml",definition)
            z.writestr(f"xl/pivotCache/pivotCacheRecords{n}.xml",records)
        return b.getvalue()


if __name__ == "__main__": unittest.main()
