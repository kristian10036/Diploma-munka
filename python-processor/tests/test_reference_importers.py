import unittest
from app.services.references import ReferenceImportError, importer_for, peak_preserving_resample


class ReferenceImporterTest(unittest.TestCase):
    def test_csv_and_json(self):
        csv_importer=importer_for("reference.csv","text/csv",b"frequency_hz,power_dbm")
        result=csv_importer.import_points(b"frequency_hz,power_dbm\n100,-90\n200,-40\n")
        self.assertEqual(result.points,[(100,-90.0),(200,-40.0)])
        json_importer=importer_for("reference.json","application/json",b"{")
        self.assertEqual(json_importer.import_points(b'{"points":[{"frequency_hz":1,"power_dbm":-90},{"frequency_hz":2,"power_dbm":-80}]}').import_format,"json")

    def test_peak_is_explicitly_unsupported(self):
        with self.assertRaises(ReferenceImportError) as raised: importer_for("sample.peak","application/octet-stream",b"unknown").import_points(b"unknown")
        self.assertEqual(raised.exception.code,"unsupported_peak_format")

    def test_resampling_preserves_peak(self):
        points=[(index,float(index==53)*100-100) for index in range(100)]
        sampled=peak_preserving_resample(points,10)
        self.assertEqual(max(power for _,power in sampled),0)


if __name__=="__main__":unittest.main()
