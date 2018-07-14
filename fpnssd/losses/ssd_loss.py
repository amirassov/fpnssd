from __future__ import print_function

import torch.nn as nn
import torch.nn.functional as F


class SSDLoss(nn.Module):
    def __init__(self, alpha=1, negative_ratio=3):
        super(SSDLoss, self).__init__()
        self.negative_ratio = negative_ratio
        self.alpha = alpha

    def _hard_negative_mining(self, label_loss, positive):
        """Return negative indices that is negative_ratio x the number as positive indices.
        Args:
          label_loss: (tensor) cross entropy losses between cls_preds and cls_targets, sized [batch_size, num_anchors].
          positive: (tensor) positive class mask, sized [batch_size, num_anchors].
        Return:
          (tensor) negative indices, sized [batch_size, num_anchors].
        """
        label_loss = label_loss * (positive.float() - 1)

        # sort by negative losses
        _, idx = label_loss.sort(1)
        # [batch_size, num_anchors]
        _, rank = idx.sort(1)

        # [batch_size,]
        num_negative = self.negative_ratio * positive.sum(1)

        # [batch_size, num_anchors]
        negative = rank < num_negative[:, None]
        return negative

    def forward(self, bbox_input, bbox_target, label_input, label_target):
        """Compute losses between (loc_preds, loc_targets) and (cls_preds, cls_targets).
        Args:
          bbox_input: (tensor) predicted locations, sized [batch_size, num_anchors, 4].
          bbox_target: (tensor) encoded target locations, sized [batch_size, num_anchors, 4].
          label_input: (tensor) predicted class confidences, sized [batch_size, num_anchors, num_classes].
          label_target: (tensor) encoded target labels, sized [batch_size, num_anchors, num_classes].
        losses:
          (tensor) losses = SmoothL1Loss(loc_preds, loc_targets) + α * CrossEntropyLoss(cls_preds, cls_targets).
        """
        # [batch_size, num_anchors]
        positive = label_target > 0
        num_positive = positive.sum().item()

        # loc_loss = SmoothL1Loss(pos_loc_preds, pos_loc_targets)
        # [ batch_size, num_anchors, 4]
        mask = positive.unsqueeze(2).expand_as(bbox_input)
        bbox_loss = F.smooth_l1_loss(bbox_input[mask], bbox_target[mask], size_average=False) / num_positive

        # cls_loss = CrossEntropyLoss(cls_preds, cls_targets)
        # [batch_size * num_anchors,]
        label_loss = F.nll_loss(label_input, label_target, reduce=False)
        # [batch_size, num_anchors]
        negative = self._hard_negative_mining(label_loss, positive)
        label_loss = label_loss[positive | negative].sum() / num_positive

        return {
            'main_loss': bbox_loss + self.alpha * label_loss,
            'bbox_loss': bbox_loss,
            'label_loss': label_loss
        }
