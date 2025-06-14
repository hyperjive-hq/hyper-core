"""Comprehensive tests for init-mcp command functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from hyper_cmd.commands.mcp_init import MCPConfigGenerator, McpInitCommand, MCPToolDetector
from hyper_cmd.container.simple_container import SimpleContainer


class TestMCPConfigGenerator:
    """Test the MCP configuration generator."""

    def test_generate_config(self):
        """Test configuration generation."""
        config = MCPConfigGenerator.generate_config()

        # Check structure
        assert "mcpServers" in config
        assert "hyper-cmd" in config["mcpServers"]
        assert "$schema" in config
        assert "version" in config
        assert "description" in config

        # Check hyper-cmd server config
        hyper_config = config["mcpServers"]["hyper-cmd"]
        assert hyper_config["command"] == "uvx"
        assert hyper_config["args"] == ["--from", ".", "hyper-mcp"]
        assert hyper_config["env"] == {}
        assert "description" in hyper_config

    def test_write_config(self):
        """Test configuration file writing."""
        config = MCPConfigGenerator.generate_config()

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "test.json"

            MCPConfigGenerator.write_config(config_file, config)

            # Verify file was created
            assert config_file.exists()

            # Verify content
            with open(config_file) as f:
                written_config = json.load(f)

            assert written_config == config

            # Verify proper formatting (should end with newline)
            with open(config_file) as f:
                content = f.read()
            assert content.endswith("\n")

    def test_read_config_nonexistent_file(self):
        """Test reading config from nonexistent file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"

            result = MCPConfigGenerator.read_config(config_file)

            assert result == {}

    def test_read_config_existing_file(self):
        """Test reading config from existing file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"
            test_config = {"mcpServers": {"test": {"command": "test"}}}

            with open(config_file, "w") as f:
                json.dump(test_config, f)

            result = MCPConfigGenerator.read_config(config_file)

            assert result == test_config

    def test_read_config_invalid_json(self):
        """Test reading config from file with invalid JSON."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"
            config_file.write_text("invalid json")

            with pytest.raises(ValueError, match="Failed to read existing config"):
                MCPConfigGenerator.read_config(config_file)

    def test_merge_config_empty_existing(self):
        """Test merging with empty existing config."""
        existing_config = {}
        new_config = MCPConfigGenerator.generate_config()

        result = MCPConfigGenerator.merge_config(existing_config, new_config)

        assert result == new_config

    def test_merge_config_with_other_servers(self):
        """Test merging config with other existing servers."""
        existing_config = {
            "mcpServers": {"other-server": {"command": "other", "args": []}},
            "version": "0.9",
        }
        new_config = MCPConfigGenerator.generate_config()

        result = MCPConfigGenerator.merge_config(existing_config, new_config)

        # Should have both servers
        assert "other-server" in result["mcpServers"]
        assert "hyper-cmd" in result["mcpServers"]
        # Should update version
        assert result["version"] == "1.0"
        # Should update schema
        assert result["$schema"] == MCPConfigGenerator.MCP_SCHEMA_URL

    def test_merge_config_update_existing_hyper_cmd(self):
        """Test merging config that updates existing hyper-cmd server."""
        existing_config = {
            "mcpServers": {
                "hyper-cmd": {"command": "old-command", "args": ["old"]},
                "other-server": {"command": "other", "args": []},
            }
        }
        new_config = MCPConfigGenerator.generate_config()

        result = MCPConfigGenerator.merge_config(existing_config, new_config)

        # Should update hyper-cmd server
        assert result["mcpServers"]["hyper-cmd"]["command"] == "uvx"
        assert result["mcpServers"]["hyper-cmd"]["args"] == ["--from", ".", "hyper-mcp"]
        # Should keep other server
        assert "other-server" in result["mcpServers"]

    def test_show_merge_preview(self):
        """Test merge preview display."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"

            existing_config = {"mcpServers": {"other-server": {"command": "other"}}}
            new_config = MCPConfigGenerator.generate_config()
            merged_config = MCPConfigGenerator.merge_config(existing_config, new_config)

            # Create a command instance for testing
            command = McpInitCommand()

            # Should not raise an exception
            command._show_merge_preview(existing_config, merged_config, config_file)


class TestMCPToolDetector:
    """Test the MCP tool detector."""

    def test_detect_tools_no_tools(self):
        """Test tool detection when no tools are present."""
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(MCPToolDetector, "_find_existing_configs", return_value=[]):
                tools = MCPToolDetector.detect_tools()
                assert tools == []

    def test_detect_tools_claude_code(self):
        """Test detection of Claude Code."""
        with patch.dict("os.environ", {"CLAUDE_CODE": "1"}):
            with patch.object(MCPToolDetector, "_find_existing_configs", return_value=[]):
                tools = MCPToolDetector.detect_tools()
                assert "Claude Code" in tools

    def test_detect_tools_existing_configs(self):
        """Test detection of existing configs."""
        mock_configs = [Path("/fake/config1.json"), Path("/fake/config2.json")]

        with patch.dict("os.environ", {}, clear=True):
            with patch.object(MCPToolDetector, "_find_existing_configs", return_value=mock_configs):
                tools = MCPToolDetector.detect_tools()
                assert any("Existing MCP configs" in tool for tool in tools)

    def test_find_existing_configs(self):
        """Test finding existing configuration files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a mock config file
            config_file = Path(tmp_dir) / ".mcp.json"
            config_file.write_text('{"test": true}')

            # Mock Path.cwd() to return our temp directory
            with patch("pathlib.Path.cwd", return_value=Path(tmp_dir)):
                # Mock Path.home() to return temp directory (to avoid real home)
                with patch("pathlib.Path.home", return_value=Path(tmp_dir)):
                    configs = MCPToolDetector._find_existing_configs()

                    # Should find our config file
                    assert any(config_file.name in str(config) for config in configs)


class TestMcpInitCommand:
    """Test the init-mcp command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.container = SimpleContainer()
        self.command = McpInitCommand(self.container)

    def test_initialization(self):
        """Test command initialization."""
        assert self.command.name == "init-mcp"
        assert "MCP" in self.command.description
        assert self.command.config_generator is not None
        assert self.command.tool_detector is not None

    def test_properties(self):
        """Test command properties."""
        assert self.command.name == "init-mcp"
        assert isinstance(self.command.description, str)
        assert isinstance(self.command.help_text, str)
        assert "init-mcp" in self.command.help_text

    def test_execute_success_force(self):
        """Test successful execution with force flag."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            exit_code = self.command.execute(force=True, config_path=tmp_dir)

            assert exit_code == 0

            # Verify config file was created
            config_file = Path(tmp_dir) / ".mcp.json"
            assert config_file.exists()

            # Verify config content
            with open(config_file) as f:
                config = json.load(f)

            assert "mcpServers" in config
            assert "hyper-cmd" in config["mcpServers"]

    def test_execute_current_directory(self):
        """Test execution in current directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Change to temp directory
            import os

            old_cwd = os.getcwd()
            try:
                os.chdir(tmp_dir)

                exit_code = self.command.execute(force=True)

                assert exit_code == 0

                # Verify config file was created in current directory
                config_file = Path(tmp_dir) / ".mcp.json"
                assert config_file.exists()

            finally:
                os.chdir(old_cwd)

    def test_execute_invalid_directory(self):
        """Test execution with invalid directory."""
        exit_code = self.command.execute(force=True, config_path="/nonexistent/directory")

        assert exit_code == 1

    def test_execute_file_as_directory(self):
        """Test execution with file path instead of directory."""
        with tempfile.NamedTemporaryFile() as tmp_file:
            exit_code = self.command.execute(force=True, config_path=tmp_file.name)

            assert exit_code == 1

    def test_determine_config_file_valid(self):
        """Test config file location determination."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = self.command._determine_config_file(tmp_dir)

            assert config_file is not None
            assert config_file.name == ".mcp.json"
            assert str(tmp_dir) in str(config_file.parent)

    def test_determine_config_file_invalid(self):
        """Test config file determination with invalid path."""
        config_file = self.command._determine_config_file("/nonexistent")

        assert config_file is None

    def test_determine_merge_strategy_no_file(self):
        """Test merge strategy when no existing file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"

            result = self.command._determine_merge_strategy(config_file, force=False)

            assert result == "overwrite"

    def test_determine_merge_strategy_with_force(self):
        """Test merge strategy with force flag."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"
            config_file.write_text('{"mcpServers": {"other": {}}}')

            result = self.command._determine_merge_strategy(config_file, force=True)

            assert result == "overwrite"

    def test_determine_merge_strategy_with_other_servers(self):
        """Test merge strategy when other servers exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"
            config_file.write_text('{"mcpServers": {"other-server": {"command": "other"}}}')

            # Mock user input to select merge
            with patch("builtins.input", return_value="1"):
                result = self.command._determine_merge_strategy(config_file, force=False)
                assert result == "merge"

            # Mock user input to select overwrite
            with patch("builtins.input", return_value="2"):
                result = self.command._determine_merge_strategy(config_file, force=False)
                assert result == "overwrite"

            # Mock user input to cancel
            with patch("builtins.input", return_value="3"):
                result = self.command._determine_merge_strategy(config_file, force=False)
                assert result is None

    def test_show_config_preview(self):
        """Test configuration preview display."""
        config = MCPConfigGenerator.generate_config()

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"

            # Should not raise an exception
            self.command._show_config_preview(config, config_file)

    def test_write_config_file_success(self):
        """Test successful config file writing."""
        config = MCPConfigGenerator.generate_config()

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"

            # Should not raise an exception
            self.command._write_config_file(config_file, config)

            assert config_file.exists()

    def test_write_config_file_permission_error(self):
        """Test config file writing with permission error."""
        config = MCPConfigGenerator.generate_config()

        # Try to write to a read-only location
        config_file = Path("/root/.mcp.json")  # Assuming this will fail

        with pytest.raises(RuntimeError):
            self.command._write_config_file(config_file, config)

    def test_confirm_overwrite_strategy_accept(self):
        """Test overwrite strategy confirmation - accept."""
        with patch("builtins.input", return_value="y"):
            result = self.command._confirm_overwrite_strategy()
            assert result == "overwrite"

        with patch("builtins.input", return_value="yes"):
            result = self.command._confirm_overwrite_strategy()
            assert result == "overwrite"

    def test_confirm_overwrite_strategy_decline(self):
        """Test overwrite strategy confirmation - decline."""
        with patch("builtins.input", return_value="n"):
            result = self.command._confirm_overwrite_strategy()
            assert result is None

        with patch("builtins.input", return_value=""):
            result = self.command._confirm_overwrite_strategy()
            assert result is None

    def test_confirm_overwrite_strategy_interrupt(self):
        """Test overwrite strategy confirmation with interrupt."""
        with patch("builtins.input", side_effect=KeyboardInterrupt()):
            result = self.command._confirm_overwrite_strategy()
            assert result is None

        with patch("builtins.input", side_effect=EOFError()):
            result = self.command._confirm_overwrite_strategy()
            assert result is None

    def test_confirm_proceed_accept(self):
        """Test proceed confirmation - accept."""
        with patch("builtins.input", return_value="y"):
            result = self.command._confirm_proceed()
            assert result is True

        with patch("builtins.input", return_value=""):
            result = self.command._confirm_proceed()
            assert result is True

    def test_confirm_proceed_decline(self):
        """Test proceed confirmation - decline."""
        with patch("builtins.input", return_value="n"):
            result = self.command._confirm_proceed()
            assert result is False

        with patch("builtins.input", return_value="no"):
            result = self.command._confirm_proceed()
            assert result is False

    def test_confirm_proceed_interrupt(self):
        """Test proceed confirmation with interrupt."""
        with patch("builtins.input", side_effect=KeyboardInterrupt()):
            result = self.command._confirm_proceed()
            assert result is False

        with patch("builtins.input", side_effect=EOFError()):
            result = self.command._confirm_proceed()
            assert result is False

    def test_execute_with_confirmation_flow(self):
        """Test execution with user confirmation flow."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create existing file
            config_file = Path(tmp_dir) / ".mcp.json"
            config_file.write_text('{"existing": true}')

            # Mock user to accept overwrite and proceed
            with patch("builtins.input", side_effect=["y", "y"]):
                exit_code = self.command.execute(force=False, config_path=tmp_dir)

                assert exit_code == 0

                # Verify new config was written
                with open(config_file) as f:
                    config = json.load(f)

                assert "hyper-cmd" in config["mcpServers"]

    def test_execute_with_cancellation(self):
        """Test execution cancelled by user."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Mock user to decline proceeding
            with patch("builtins.input", return_value="n"):
                exit_code = self.command.execute(force=False, config_path=tmp_dir)

                assert exit_code == 1

                # Verify no config file was created
                config_file = Path(tmp_dir) / ".mcp.json"
                assert not config_file.exists()

    def test_execute_exception_handling(self):
        """Test exception handling during execution."""
        # Mock an exception in config generation
        with patch.object(
            self.command.config_generator, "generate_config", side_effect=Exception("Test error")
        ):
            exit_code = self.command.execute(force=True, config_path="/tmp")

            assert exit_code == 1

    def test_execute_uvx_not_available(self):
        """Test execution when uvx is not available."""
        with patch("shutil.which", return_value=None):
            exit_code = self.command.execute(force=True, config_path="/tmp")

            assert exit_code == 1

    def test_execute_uvx_available(self):
        """Test execution when uvx is available."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("shutil.which", return_value="/usr/bin/uvx"):
                exit_code = self.command.execute(force=True, config_path=tmp_dir)

                assert exit_code == 0

    def test_show_next_steps(self):
        """Test next steps display."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / ".mcp.json"

            # Should not raise an exception
            self.command._show_next_steps(config_file)

    def test_integration_with_mcp_server(self):
        """Test integration between mcp-init and MCP server."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create config with mcp-init
            exit_code = self.command.execute(force=True, config_path=tmp_dir)
            assert exit_code == 0

            # Verify config file
            config_file = Path(tmp_dir) / ".mcp.json"
            assert config_file.exists()

            # Load and verify config structure matches MCP server expectations
            with open(config_file) as f:
                config = json.load(f)

            assert "mcpServers" in config
            server_config = config["mcpServers"]["hyper-cmd"]
            assert server_config["command"] == "uvx"

            # Verify config has required fields for MCP
            assert "$schema" in config
            assert "version" in config


class TestMCPInitIntegration:
    """Integration tests for mcp-init command."""

    def test_command_available_in_registry(self):
        """Test that init-mcp command is properly registered."""
        from hyper_cmd.cli import discover_commands

        registry = discover_commands()
        commands = registry.list_commands()

        assert "init-mcp" in commands

        # Test command can be retrieved and instantiated
        cmd_class = registry.get("init-mcp")
        assert cmd_class is not None

        container = SimpleContainer()
        instance = cmd_class(container)
        assert instance.name == "init-mcp"

    def test_command_available_via_mcp(self):
        """Test that init-mcp command is available via MCP server."""
        from hyper_cmd.mcp_server import MCPServer

        server = MCPServer()
        tools = server.get_tools()

        # Should find init-mcp tool
        mcp_init_tools = [tool for tool in tools if tool["name"] == "hyper_init-mcp"]
        assert len(mcp_init_tools) == 1

        tool = mcp_init_tools[0]
        assert "Initialize MCP configuration" in tool["description"]
        assert "inputSchema" in tool

    def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow."""
        from hyper_cmd.mcp_server import MCPServer

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Execute init-mcp via MCP server
            server = MCPServer()

            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "hyper_init-mcp",
                    "arguments": {"force": True, "config_path": tmp_dir},
                },
            }

            response = server.handle_request(request)

            # 2. Verify MCP response
            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 1
            assert "result" in response
            assert "isError" not in response["result"]

            # 3. Verify config file was created
            config_file = Path(tmp_dir) / ".mcp.json"
            assert config_file.exists()

            # 4. Verify config content
            with open(config_file) as f:
                config = json.load(f)

            assert "mcpServers" in config
            assert "hyper-cmd" in config["mcpServers"]
            assert config["mcpServers"]["hyper-cmd"]["command"] == "uvx"
