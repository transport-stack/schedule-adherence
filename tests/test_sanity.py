import unittest
import os

class TestSanity(unittest.TestCase):

    def test_required_directories_exist(self):
        """Check if required directories are present."""
        self.assertTrue(os.path.isdir('route_comp'), "'route_comp' directory not found.")
        self.assertTrue(os.path.isdir('route_comp/data'), "'route_comp/data' directory not found.")

    def test_env_example_exists(self):
        """Check if the .env.example file exists."""
        self.assertTrue(os.path.isfile('.env.example'), "'.env.example' file not found.")

if __name__ == '__main__':
    unittest.main()
