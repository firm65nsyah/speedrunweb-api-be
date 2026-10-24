import unittest
from api.index import app

class SpeedrunApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_01_root_endpoint(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json.get('status'), 'success')

    def test_02_health_check(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        self.assertIn('database', res.json)

    def test_03_get_genres(self):
        res = self.client.get('/api/genres')
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.json.get('total', 0), 0)

    def test_04_get_games(self):
        res = self.client.get('/api/games')
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.json.get('total', 0), 0)

    def test_05_get_game_detail_success(self):
        res = self.client.get('/api/games/1')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['data']['id'], 1)

    def test_06_get_game_detail_not_found(self):
        res = self.client.get('/api/games/9999')
        self.assertEqual(res.status_code, 404)

    def test_07_create_game_success(self):
        payload = {
            "name": "Portal 2",
            "genre_id": 1,
            "description": "First-person puzzle platformer."
        }
        res = self.client.post('/api/games', json=payload)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json['data']['name'], "Portal 2")

    def test_08_create_game_missing_name(self):
        res = self.client.post('/api/games', json={"genre_id": 1})
        self.assertEqual(res.status_code, 400)

    def test_09_update_game_success(self):
        res = self.client.put('/api/games/1', json={"description": "Deskripsi baru"})
        self.assertEqual(res.status_code, 200)

    def test_10_delete_game_conflict(self):
        # Game ID 1 memiliki kategori di mock data -> harus 409 Conflict
        res = self.client.delete('/api/games/1')
        self.assertEqual(res.status_code, 409)

    def test_11_get_categories(self):
        res = self.client.get('/api/categories')
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.json.get('total', 0), 0)

    def test_12_get_leaderboard(self):
        res = self.client.get('/api/leaderboard')
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.json.get('total', 0), 0)

if __name__ == '__main__':
    unittest.main()
