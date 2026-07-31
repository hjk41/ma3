from src.app import main


def test_main(capsys):
    main()
    assert "hello" in capsys.readouterr().out
