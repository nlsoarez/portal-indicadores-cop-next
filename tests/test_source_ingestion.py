import io
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd


from tests.isolated_database import isolate_sqlite_database

class SourceIngestionTest(unittest.TestCase):
    def setUp(self):
        isolate_sqlite_database(self)
        from src.config.seed import seed_foundation
        seed_foundation()
        from src.application.access_service import AccessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        self.users = UserRepository(); self.segment = SegmentRepository().get_by_slug("preventiva")
        self.ctx = AccessService(self.users).context(self.users.get_by_login("ADMIN").id)


    @staticmethod
    def _xlsx(df: pd.DataFrame, sheet: str, startrow: int = 0) -> bytes:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet, index=False, startrow=startrow)
        return buffer.getvalue()

    def test_chat_upload_filters_scope_and_persists_daily_result_and_freshness(self):
        from src.application.upload_service import UploadProcessingService
        from src.infrastructure.repositories import IndicatorRepository
        df = pd.DataFrame({
            "FECHAMENTO_COPREDE_LOGIN_ANALISTA":["N5604148","N5604148","N5941223","OUTSIDE","N0158974"],
            "ABERTURA_ANOMES":[202609,202609,202609,202609,202608],
            "FECHAMENTO_FILA":["COP REDE COAXIAL SUPORTE QOE"]*5,
            "INDICADOR_TMA_DENTRO":[1,0,1,1,1],
            "CHAT_INICIO":["2026-09-28 22:10:00","2026-09-28 22:20:00","2026-09-28 23:10:00","2026-09-28 23:20:00","2026-08-31 23:00:00"],
        })
        result=UploadProcessingService().process(self.ctx,self.segment.id,"chat_toa","chat.xlsx",self._xlsx(df,"Analítico CHAT TOA",3))
        self.assertEqual("2026-09-28",result.data_through); self.assertEqual(2,result.analyst_count); self.assertEqual(3,result.total_volume)
        daniel=self.users.get_by_login("N5604148"); repo=IndicatorRepository()
        chat=next(r for r in repo.results_for_user(self.segment.id,daniel.id) if r["indicator_key"]=="chat_10m")
        self.assertEqual(50.0,chat["value"]); self.assertEqual(2,chat["volume"])
        fresh=next(r for r in repo.freshness(self.segment.id) if r["indicator_key"]=="chat_10m")
        self.assertEqual("2026-09-28",fresh["data_through"]); self.assertEqual("chat.xlsx",fresh["filename"])

    def test_validation_compatibility_route(self):
        from src.application.upload_service import UploadProcessingService
        from src.infrastructure.repositories import IndicatorRepository
        df=pd.DataFrame({
            "INDICADOR_NOME":["TEMPO DE VALIDAÇÃO DO FORMULÁRIO"]*3,
            "LOGIN":["N5577565","N5577565","N0158974"],
            "INDICADOR":[1,1,0],"ANOMES":[202609]*3,"IN_REGIONAL":["Leste"]*3,
            "DATA":["2026-09-27","2026-09-29","2026-09-29"],
        })
        result=UploadProcessingService().process(self.ctx,self.segment.id,"toa_validation","validacao.xlsx",self._xlsx(df,"TOA"))
        self.assertEqual("2026-09-29",result.data_through)
        carlos=self.users.get_by_login("N0158974")
        val=next(r for r in IndicatorRepository().results_for_user(self.segment.id,carlos.id) if r["indicator_key"]=="validacao_20m")
        self.assertEqual(0.0,val["value"])

    def test_reupload_same_month_replaces_old_days(self):
        from src.application.upload_service import UploadProcessingService
        from src.infrastructure.repositories import IndicatorRepository
        service=UploadProcessingService()
        first=pd.DataFrame({"FECHAMENTO_COPREDE_LOGIN_ANALISTA":["N5604148","N5604148"],"ABERTURA_ANOMES":[202609,202609],"INDICADOR_TMA_DENTRO":[1,0],"CHAT_INICIO":["2026-09-27 22:00:00","2026-09-28 22:00:00"]})
        second=pd.DataFrame({"FECHAMENTO_COPREDE_LOGIN_ANALISTA":["N5604148"],"ABERTURA_ANOMES":[202609],"INDICADOR_TMA_DENTRO":[1],"CHAT_INICIO":["2026-09-29 22:00:00"]})
        service.process(self.ctx,self.segment.id,"chat_toa","chat-1.xlsx",self._xlsx(first,"Analítico CHAT TOA",3))
        service.process(self.ctx,self.segment.id,"chat_toa","chat-2.xlsx",self._xlsx(second,"Analítico CHAT TOA",3))
        daniel=self.users.get_by_login("N5604148")
        rows=[r for r in IndicatorRepository().results_for_user(self.segment.id,daniel.id) if r["indicator_key"]=="chat_10m"]
        self.assertEqual(1,len(rows)); self.assertEqual("2026-09-29",rows[0]["period"]); self.assertEqual(100.0,rows[0]["value"])

    def test_subadmin_cannot_process_upload(self):
        from src.application.access_service import AccessService
        from src.application.upload_service import UploadProcessingService
        leader=self.users.get_by_login("N0238475"); ctx=AccessService(self.users).context(leader.id)
        df=pd.DataFrame({"FECHAMENTO_COPREDE_LOGIN_ANALISTA":["N5604148"],"ABERTURA_ANOMES":[202609],"INDICADOR_TMA_DENTRO":[1],"CHAT_INICIO":["2026-09-29 22:00:00"]})
        with self.assertRaises(PermissionError):
            UploadProcessingService().process(ctx,self.segment.id,"chat_toa","bloqueado.xlsx",self._xlsx(df,"Analítico CHAT TOA",3))


if __name__ == "__main__": unittest.main()
