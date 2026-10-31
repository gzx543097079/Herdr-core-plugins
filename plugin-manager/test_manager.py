import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('manager',Path(__file__).with_name('server.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class CompositionTests(unittest.TestCase):
    def exercise(self,plugin,action,enabled):
        wanted=dict(enabled);wanted[plugin]=action=='install'
        before={'running':True,'layout':'desktop-motion-layout','plugins':enabled}
        after={'running':True,'plugins':wanted}
        with patch.object(m,'status',side_effect=[before,after]), patch.object(m,'chain',return_value=['desktop-motion-layout','agent-history-layout','main-i18n']), patch.object(m,'layout',return_value={'_motion_base':'agent-history-layout','_history_base':'main-i18n'}), patch.object(m,'switch',return_value='ok') as switch, patch.object(m,'run',return_value='ok') as run:
            m.apply_base(plugin,action)
            commands=[' '.join(map(str,c.args[0])) for c in run.call_args_list]
            if plugin=='language':
                self.assertEqual(any('agent-history/install.py' in c for c in commands),wanted['history'])
                self.assertEqual(any('desktop-motion/install.py' in c for c in commands),wanted['motion'])
            if plugin=='motion':
                self.assertFalse(any('agent-history/install.py' in c for c in commands))
                self.assertEqual(any('desktop-motion/install.py' in c for c in commands),action=='install')
            return commands
    def test_remove_history_keeps_motion_and_language(self):
        self.exercise('history','uninstall',dict(history=True,motion=True,language=True))
    def test_remove_motion_keeps_history(self):
        self.exercise('motion','uninstall',dict(history=True,motion=True,language=True))
    def test_language_removal_rebuilds_enabled_plugins(self):
        calls=self.exercise('language','uninstall',dict(history=True,motion=True,language=True))
        self.assertTrue(any('herdr_lang.py uninstall' in c for c in calls))
    def test_reinjection(self):
        self.exercise('history','install',dict(history=True,motion=True,language=True))
    def test_unknown_action_rejected_before_commands(self):
        with patch.object(m,'run') as run:
            with self.assertRaises(ValueError):m.apply('history','shell')
            run.assert_not_called()
    def test_offline_does_not_mutate(self):
        with patch.object(m,'status',return_value={'running':False}),patch.object(m,'switch') as switch:
            with self.assertRaises(RuntimeError):m.apply('history','install')
            switch.assert_not_called()

class CommandCompositionTests(unittest.TestCase):
    def test_other_plugin_is_unwrapped_then_restored(self):
        before={'running':True,'plugins':{'commands':True}}
        with patch.object(m,'status',return_value=before),patch.object(m,'layout',return_value={'_commands_base':'base'}),patch.object(m,'switch') as switch,patch.object(m,'apply_base',return_value={}) as base,patch.object(m,'run') as run:
            m.apply('history','uninstall')
            switch.assert_called_once_with('base');base.assert_called_once_with('history','uninstall')
            self.assertIn('command-hints/install.py',str(run.call_args))
    def test_failure_restores_commands(self):
        with patch.object(m,'status',return_value={'running':True,'plugins':{'commands':True}}),patch.object(m,'layout',return_value={'_commands_base':'base'}),patch.object(m,'switch'),patch.object(m,'apply_base',side_effect=RuntimeError('failed')),patch.object(m,'run') as run:
            with self.assertRaises(RuntimeError):m.apply('motion','install')
            self.assertIn('command-hints/install.py',str(run.call_args))

if __name__=='__main__':unittest.main()
