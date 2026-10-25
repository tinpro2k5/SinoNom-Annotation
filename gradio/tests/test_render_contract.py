"""Check real Gradio callback outputs without a server or filesystem fixtures."""
import inspect
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from annotation.bbox import add_bbox
from annotation.state import new_state, set_verified_content, initialize_alignment


class RenderContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent
        cls.image = cls.root / 'render-fixture.png'
        cls.title = 'Nguyên văn chữ Hán Nôm'
        cls.engine = Mock()
        cls.engine.preview_dir = cls.root
        cls.engine.content_titles = (cls.title,)
        cls.engine.metadata_fields = ()
        options = SimpleNamespace(image_dir=str(cls.root), source_json='unused.json',
                                  output_dir=str(cls.root / 'unused-output'), skip_detection=True)
        with patch('app.resolve_app_paths', return_value=options), \
                patch('app.Workflow', return_value=cls.engine), \
                patch('app.load_image_list', return_value=[cls.image]), \
                patch('app.read_json', return_value=[]):
            cls.app = create_app(options)
        cls.open_event = next(event for event in cls.app.fns.values()
                              if event.fn and event.fn.__name__ == 'open_image')
        cls.render = staticmethod(inspect.getclosurevars(cls.open_event.fn).nonlocals['render'])

    def state(self, step):
        if step == 1:
            return new_state()
        record = {'noi_dung': [{'ky_hieu': '1', 'chuyen_muc': [
            {'tieu_de': self.title, 'van_ban': '永寺'}]}]}
        state = new_state()
        state.update(image=self.image.name, image_path=None, image_url='fixture.png',
                     code='1', image_size=[100, 100], resized_image_size=[100, 100],
                     crop=[0, 0, 100, 100], source_content=deepcopy(record),
                     source_baseline=deepcopy(record), draft_content=deepcopy(record))
        set_verified_content(state, record, '永寺')
        for x in (10, 40):
            add_bbox(state, [x, 10, x + 20, 30])
        initialize_alignment(state, ordered_uids=list(state['regions']))
        state['workflow'] = {key: True for key in state['workflow']}
        state['current_step'] = step
        return state

    def assert_outputs(self, result):
        self.assertEqual(len(result), len(self.open_event.outputs),
                         'Every declared component needs its own returned output slot')
        self.app.validate_outputs(self.open_event, result)
        picker_index = next(index for index, component in enumerate(self.open_event.outputs)
                            if component.get_block_name() == 'dropdown' and component.label == 'Image')
        draft_index = next(index for index, component in enumerate(self.open_event.outputs)
                           if component.elem_id == 'save-draft-button')
        self.assertEqual(result[picker_index], {'value': None, '__type__': 'update'})
        self.assertEqual(result[draft_index]['__type__'], 'update')

    def test_render_all_workflow_steps(self):
        for step in (1, 2, 3, 4, 5, 6, 7):
            with self.subTest(step=step):
                state = self.state(step)
                before = deepcopy(state)
                result = self.render({'active': state, 'drafts': {}})
                self.assert_outputs(result)
                self.assertEqual(state['annotations'], before['annotations'])
                self.assertEqual(state['bounding_boxes'], before['bounding_boxes'])

    def test_open_fresh_image_and_restored_step4(self):
        for step in (2, 4):
            with self.subTest(step=step):
                self.engine.open_image.return_value = self.state(step)
                result = self.open_event.fn({'active': new_state(), 'drafts': {}}, str(self.image))
                self.assert_outputs(result)
                self.assertEqual(result[0]['active']['current_step'], step)
        self.engine.save_draft.assert_not_called()
        self.engine.apply.assert_not_called()

    def test_open_error_still_returns_all_outputs(self):
        with patch('app.gr.Warning'), patch('app.log.exception'):
            result = self.open_event.fn({'active': new_state(), 'drafts': {}}, 'not-listed.png')
        self.assert_outputs(result)
        self.assertEqual(result[0]['active']['current_step'], 1)


if __name__ == '__main__':
    unittest.main()
