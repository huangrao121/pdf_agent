"""
Unit tests for anchor locator validation.
"""
import pytest
from pydantic import ValidationError

from pdf_ai_agent.api.schemas.document_schemas import (
    AnchorLocator,
    CreateAnchorRequest,
)


class TestAnchorLocatorValidation:
    """Test anchor locator validation logic."""

    def test_valid_locator(self):
        """Test valid locator passes validation."""
        locator = AnchorLocator(
            type="pdf_quadpoints",
            coord_space="pdf_points",
            page=12,
            quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
        )
        assert locator.type == "pdf_quadpoints"
        assert locator.coord_space == "pdf_points"
        assert locator.page == 12
        assert len(locator.quads) == 1
        assert len(locator.quads[0]) == 8

    def test_invalid_locator_type(self):
        """Test invalid locator type fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            AnchorLocator(
                type="invalid_type",
                coord_space="pdf_points",
                page=12,
                quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
            )
        assert "Locator type must be" in str(exc_info.value)

    def test_invalid_coord_space(self):
        """Test invalid coordinate space fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            AnchorLocator(
                type="pdf_quadpoints",
                coord_space="invalid_space",
                page=12,
                quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
            )
        assert "Coordinate space must be" in str(exc_info.value)

    def test_invalid_quad_length(self):
        """Test quad with wrong number of coordinates fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            AnchorLocator(
                type="pdf_quadpoints",
                coord_space="pdf_points",
                page=12,
                quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1]],  # Only 7 values
            )
        assert "must have exactly 8 numbers" in str(exc_info.value)

    def test_invalid_quad_infinite(self):
        """Test quad with infinite value fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            AnchorLocator(
                type="pdf_quadpoints",
                coord_space="pdf_points",
                page=12,
                quads=[[72.1, 512.3, float("inf"), 512.3, 310.4, 498.2, 72.1, 498.2]],
            )
        assert "must be finite numbers" in str(exc_info.value)

    def test_invalid_quad_nan(self):
        """Test quad with NaN value fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            AnchorLocator(
                type="pdf_quadpoints",
                coord_space="pdf_points",
                page=12,
                quads=[[72.1, 512.3, float("nan"), 512.3, 310.4, 498.2, 72.1, 498.2]],
            )
        assert "must be finite numbers" in str(exc_info.value)

    def test_multiple_quads(self):
        """Test multiple quads are accepted."""
        locator = AnchorLocator(
            type="pdf_quadpoints",
            coord_space="pdf_points",
            page=12,
            quads=[
                [72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2],
                [72.1, 482.3, 310.4, 482.3, 310.4, 468.2, 72.1, 468.2],
            ],
        )
        assert len(locator.quads) == 2

    def test_page_zero_invalid(self):
        """Test page 0 fails validation (must be >= 1)."""
        with pytest.raises(ValidationError) as exc_info:
            AnchorLocator(
                type="pdf_quadpoints",
                coord_space="pdf_points",
                page=0,
                quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
            )
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_negative_page_invalid(self):
        """Test negative page fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            AnchorLocator(
                type="pdf_quadpoints",
                coord_space="pdf_points",
                page=-1,
                quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
            )
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_empty_quads_invalid(self):
        """Test empty quads list fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            AnchorLocator(
                type="pdf_quadpoints",
                coord_space="pdf_points",
                page=12,
                quads=[],  # Empty list
            )
        assert "at least 1" in str(exc_info.value).lower()


class TestCreateAnchorRequestValidation:
    """Test CreateAnchorRequest validation logic."""

    def test_valid_request(self):
        """Test valid request passes validation."""
        request = CreateAnchorRequest(
            chunk_id=456,
            doc_id=22222,
            page=12,
            quoted_text="The model uses scaled dot-product attention.",
            locator=AnchorLocator(
                type="pdf_quadpoints",
                coord_space="pdf_points",
                page=12,
                quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
            ),
        )
        assert request.page == 12
        assert request.locator.page == 12

    def test_page_mismatch_fails(self):
        """Test page mismatch between body and locator fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            CreateAnchorRequest(
                chunk_id=456,
                doc_id=22222,
                page=12,
                quoted_text="The model uses scaled dot-product attention.",
                locator=AnchorLocator(
                    type="pdf_quadpoints",
                    coord_space="pdf_points",
                    page=13,  # Different from body page
                    quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                ),
            )
        assert "Locator page must match" in str(exc_info.value)

    def test_optional_chunk_id(self):
        """Test chunk_id is optional."""
        request = CreateAnchorRequest(
            doc_id=22222,
            page=12,
            quoted_text="The model uses scaled dot-product attention.",
            locator=AnchorLocator(
                type="pdf_quadpoints",
                coord_space="pdf_points",
                page=12,
                quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
            ),
        )
        assert request.chunk_id is None

    def test_page_zero_in_request_fails(self):
        """Test page 0 in request fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            CreateAnchorRequest(
                doc_id=22222,
                page=0,
                quoted_text="The model uses scaled dot-product attention.",
                locator=AnchorLocator(
                    type="pdf_quadpoints",
                    coord_space="pdf_points",
                    page=0,
                    quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                ),
            )
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_empty_quoted_text_fails(self):
        """Test empty quoted_text fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            CreateAnchorRequest(
                doc_id=22222,
                page=12,
                quoted_text="",  # Empty string
                locator=AnchorLocator(
                    type="pdf_quadpoints",
                    coord_space="pdf_points",
                    page=12,
                    quads=[[72.1, 512.3, 310.4, 512.3, 310.4, 498.2, 72.1, 498.2]],
                ),
            )
        assert "at least 1" in str(exc_info.value).lower()
